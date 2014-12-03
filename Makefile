ifdef B_BASE
include $(B_BASE)/common.mk
include $(B_BASE)/rpmbuild.mk
endif

xscontainer: all

all: build

build: clean
	python setup.py bdist_rpm --install-script install.spec
ifdef MY_OUTPUT_DIR
	mkdir -p $(MY_OUTPUT_DIR)/SRPMS
	cp dist/*.noarch.rpm $(MY_OUTPUT_DIR)
	cp dist/*.src.rpm $(MY_OUTPUT_DIR)/SRPMS
endif

clean:
	python setup.py clean
	if [ -d "build" ]; then \
		rm -rf build; \
	fi
	if [ -d "dist" ]; then \
		rm -rf dist; \
	fi
	exit 0
