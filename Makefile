lint:
	pip3 install flake8==3.7.7 pycodestyle==2.5.0 black==19.10b0
	flake8 --max-line-length 120 src tests
	pycodestyle --hang-closing --max-line-length=120 --exclude=conf.py ./**/*.py
	black --check --diff ./src ./test
