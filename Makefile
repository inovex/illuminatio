lint:
	pip3 install flake8==3.7.7 pycodestyle==2.5.0
	flake8 --max-line-length 120 src tests
	pycodestyle --hang-closing --max-line-length=120 --exclude=conf.py ./**/*.py

image-build:
	docker build -t $(IMAGE_REPO)/illuminatio-runner:$(IMAGE_TAG) -f illuminatio-runner.dockerfile .
	docker build -t $(IMAGE_REPO)/illuminatio:$(IMAGE_TAG) .

image-push:
	docker push $(IMAGE_REPO)/illuminatio-runner:$(IMAGE_TAG)
	docker push $(IMAGE_REPO)/illuminatio:$(IMAGE_TAG)
