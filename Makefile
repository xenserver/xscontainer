VERSION ?= 0.1
RELEASE ?= 1
MY_OUTPUT_DIR ?= dist/

all:
	python setup.py build

bdist_rpm:
ifeq ($(shell rpm -q centos-release --qf '%{version}\n'),7)
	# @ToDo: ugly workaround - can't get distutils otherwise to avoid using
	# /var/tmp
	mkdir -p temp
	mount -o bind temp /var/tmp/
endif
	python setup.py bdist_rpm --forceversion=$(VERSION) --release=$(RELEASE) \
		--install-script mk/install-script \
		--dist-dir $(MY_OUTPUT_DIR)
ifeq ($(shell rpm -q centos-release --qf '%{version}\n'),7)
	# @ToDo: part of the workaround in the above
	umount /var/tmp
	rmdir temp
endif

install:
	python setup.py install

clean:
	python setup.py clean
	rm -rf build
