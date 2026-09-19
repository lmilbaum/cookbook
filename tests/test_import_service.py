"""Test application imports without contacting Instagram."""
from __future__ import annotations

import io
import subprocess
import threading

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cookbook import import_service, post_import_job, server
from cookbook.database import Base
from cookbook.models import Post, Recipe
from cookbook.post_repository import (
    insert_missing_recipes,
    load_recipes,
    mark_not_recipe,
)


def test_import_selects_one_unseen_post_and_preserves_existing_data(tmp_path, monkeypatch):
    (tmp_path / 'cookbook.toml').write_text('username = "example"\nlimit = 9\nignore_cached_posts = true\n')
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def recipe(code):
        item = Recipe(id=code, image_url='', caption='', timestamp_utc='2026-01-01')
        item.post = Post(shortcode=code, url='https://example.com', typename='GraphImage', is_video=False)
        return item
    insert_missing_recipes(factory, [recipe('hidden'), recipe('known')])
    mark_not_recipe(factory, 'hidden')
    calls = []
    cached = []
    def fetch(username, **kwargs):
        calls.append(kwargs)
        return [recipe('next')]
    monkeypatch.setattr(post_import_job, 'fetch_posts_browser', fetch)
    monkeypatch.setattr(post_import_job, '_cache_images_for_report', lambda recipes, path: cached.append(recipes))
    monkeypatch.setattr(post_import_job, 'load_dotenv', lambda *args: None)
    assert post_import_job.import_next_post(tmp_path, factory) == 1
    assert calls[0]['seen_shortcodes'] == {'hidden', 'known'}
    assert calls[0]['feed_position_from_end'] == 1
    assert calls[0]['limit'] == 1 and calls[0]['headless'] is True
    assert {item.id for item in load_recipes(factory, False)} == {'known', 'next'}
    assert len(cached) == 1
    assert post_import_job.import_next_post(tmp_path, factory) == 0
    assert len(cached) == 1
    engine.dispose()


@pytest.mark.parametrize('code,status', [(0, 'succeeded'), (3, 'empty'), (1, 'failed'), (4, 'failed')])
def test_worker_outcomes_do_not_expose_scraper_output(tmp_path, monkeypatch, code, status):
    refreshed = []
    monkeypatch.setattr(import_service, 'run_scraper', lambda root: code)
    service = import_service.ImportService(tmp_path, lambda: refreshed.append(True))
    service._run()
    assert service.status()['status'] == status
    assert bool(refreshed) == (code == 0)


def test_worker_rejects_overlapping_requests_and_allows_retry(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def run(*args, **kwargs):
        entered.set()
        release.wait(3)
        return 3
    monkeypatch.setattr(import_service, 'run_scraper', run)
    service = import_service.ImportService(tmp_path, lambda: None)
    assert service.start()
    assert entered.wait(2)
    assert not service.start()
    assert service.status()['status'] == 'running'
    release.set()


def test_timeout_is_reported_without_private_details(tmp_path, monkeypatch):
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired('private details', 1800)
    monkeypatch.setattr(import_service, 'run_scraper', run)
    service = import_service.ImportService(tmp_path, lambda: None)
    service._run()
    assert service.status()['status'] == 'failed'
    assert 'timed out' in service.status()['message']
    assert 'private details' not in service.status()['message']


def test_import_http_status_and_duplicate_request(tmp_path, monkeypatch):
    class FakeService:
        running = False
        def __init__(self, *args): pass
        def status(self): return {'status': 'running' if self.running else 'idle', 'message': ''}
        def start(self):
            if self.running: return False
            self.running = True
            return True
    monkeypatch.setattr(server, 'ImportService', FakeService)
    handler = object.__new__(server.make_handler(tmp_path, None))
    handler.path = '/api/import-post'
    responses = []
    handler._json_response = lambda code, body: responses.append((code, body))
    handler.do_GET()
    assert responses.pop()[1]['status'] == 'idle'
    def post(body, content_type='application/json'):
        handler.headers = {'Content-Length': str(len(body)), 'Content-Type': content_type}
        handler.rfile = io.BytesIO(body)
        handler.do_POST()
        return responses.pop()[0]
    assert post(b'{}', 'text/plain') == 400
    assert post(b'{"command":"anything"}') == 400
    assert post(b'{}') == 202
    assert post(b'{}') == 409


def test_timeout_terminates_browser_process_group(tmp_path, monkeypatch):
    killed = []
    class Process:
        pid = 12345
        returncode = -9
        calls = 0
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def communicate(self, timeout=None):
            self.calls += 1
            if timeout is not None:
                assert timeout == 1800
                raise subprocess.TimeoutExpired('worker', timeout)
    def popen(command, **kwargs):
        assert command[1:3] == ['-m', 'cookbook.post_import_job']
        assert kwargs['start_new_session'] is True
        assert kwargs['stdout'] == kwargs['stderr'] == subprocess.DEVNULL
        return Process()
    monkeypatch.setattr(import_service.subprocess, 'Popen', popen)
    monkeypatch.setattr(import_service.os, 'killpg', lambda pid, sig: killed.append(pid))
    with pytest.raises(subprocess.TimeoutExpired):
        import_service.run_scraper(tmp_path)
    assert killed == [12345]
