.PHONY: up down

up:
	docker compose up -d --build --wait

down:
	docker compose down
