lint:
	@rm -rf ./public
	pip3 install flake8==3.7.7 pycodestyle==2.5.0 black==19.10b0 anybadge==1.1.1 pylint==2.5.3 pylint-exit==1.2.0
	flake8 --max-line-length 120 src tests
	pycodestyle --max-line-length=120 --exclude=conf.py ./**/*.py
	black --check --diff ./src ./tests
	pylint --rcfile=.pylintrc --output-format=text src | tee pylint.txt
	mkdir -p public
	anybadge --value=$$(sed -n 's/^Your code has been rated at \([-0-9.]*\)\/.*/\1/p' pylint.txt) --file=public/pylint.svg pylint
	mv pylint.txt public/pylint.txt

fmt:
	black --diff ./src ./tests
