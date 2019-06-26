lint:
	pip3 install flake8==3.7.7 pycodestyle==2.5.0
	flake8 --max-line-length 120 src tests
	pycodestyle --hang-closing --max-line-length=120 --exclude=conf.py ./**/*.py
