VERSION ?= 0.1
RELEASE ?= 1
MY_OUTPUT_DIR ?= dist/

all:
	python setup.py build

bdist_rpm:
	python setup.py bdist_rpm --forceversion=$(VERSION) --release=$(RELEASE) \
		--install-script mk/install-script \
		--dist-dir $(MY_OUTPUT_DIR)

install:
	python setup.py install

clean:
	python setup.py clean
	rm -rf build
