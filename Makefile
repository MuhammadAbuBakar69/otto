.PHONY: help demo test lint run dashboard docker clean

help:
	@echo "make demo       seed invented data and print the outbox"
	@echo "make test       run the test suite (no network)"
	@echo "make lint       ruff (pip install ruff)"
	@echo "make run        the heartbeat, one cycle"
	@echo "make dashboard  the outbox UI on 127.0.0.1:5555"
	@echo "make docker     build the image"
	@echo "make clean      delete data/otto.db"

demo:
	python3 -m otto demo --reset
	python3 -m otto status

test:
	python3 -m unittest discover -s tests -v

lint:
	ruff check otto tests

run:
	python3 -m otto run --once

dashboard:
	python3 -m otto dashboard

docker:
	docker build -t otto:latest .

clean:
	rm -rf data/otto.db
