USE_BRANDING := yes
IMPORT_BRANDING := yes
IMPORT_VERSIONS := yes
include $(B_BASE)/common.mk
include $(B_BASE)/rpmbuild.mk

REPO = $(call git_loc,xscontainer)
RPM_BINDIR = $(RPM_RPMSDIR)/$(DOMAIN0_ARCH_OPTIMIZED)
CSET_NUMBER := $(shell $(shell $(call git_cset_number,xscontainer)); echo $$CSET_NUMBER)
VERSION := $(PRODUCT_VERSION)
RELEASE := $(BUILD_NUMBER)

COMPLETE_VERSION := $(VERSION)-$(RELEASE)


RPMPREFIX := xscontainer-$(COMPLETE_VERSION)
RPM := $(RPMPREFIX).noarch.rpm
SRPM := $(RPMPREFIX).src.rpm
SUPP_PACK := $(MY_OUTPUT_DIR)/xscontainer-$(COMPLETE_VERSION)
SUPP_PACK_SOURCES := $(MY_OUTPUT_DIR)/xscontainer-sources-$(COMPLETE_VERSION).iso
XSCONTAINER_STAMP := $(MY_OBJ_DIR)/.rpmbuild.stamp


# packages installed on dom0
DOM0_RPMS :=
# source packages
DOM0_SRPMS  :=

PARAMIKO_NAME = python-paramiko
PARAMIKO_VERSION = 1.7.6-1
PARAMIKO_FULLNAME = $(PARAMIKO_NAME)-$(PARAMIKO_VERSION)
PARAMIKO_SOURCE = /distfiles/xscontainer/epel/2015-02-13/5/SRPMS/$(PARAMIKO_FULLNAME).el5.src.rpm
GMP_NAME = gmp
GMP_VERSION = 5.1.1-5
GMP_FULLNAME = $(GMP_NAME)-$(GMP_VERSION)
GMP_SOURCE = /distros/CentOS/7.0.1406/os/Source/SPackages/$(GMP_FULLNAME).el7.src.rpm
PYCRYPTO_NAME = python-crypto
PYCRYPTO_VERSION = 2.6.1-1
PYCRYPTO_FULLNAME = $(PYCRYPTO_NAME)-$(PYCRYPTO_VERSION)
PYCRYPTO_SOURCE = /distros/CentOS/7.0.1406/EPEL-20140902/SRPMS/p/$(PYCRYPTO_FULLNAME).el7.src.rpm

DOM0_RPMS += /distros/CentOS/5.10/os/$(DOMAIN0_ARCH)/CentOS/mkisofs-2.01-10.7.el5.$(DOMAIN0_ARCH).rpm
DOM0_SRPMS += /distros/CentOS/5.10/os/SRPMS/cdrtools-2.01-10.7.el5.src.rpm
DOM0_RPMS += /usr/src/redhat/RPMS/noarch/$(PARAMIKO_FULLNAME).noarch.rpm
DOM0_SRPMS += $(PARAMIKO_SOURCE)
DOM0_RPMS += /usr/src/redhat/RPMS/$(DOMAIN0_ARCH)/$(GMP_FULLNAME).$(DOMAIN0_ARCH).rpm
DOM0_SRPMS += $(GMP_SOURCE)
DOM0_RPMS += /usr/src/redhat/RPMS/$(DOMAIN0_ARCH)/$(PYCRYPTO_FULLNAME).$(DOMAIN0_ARCH).rpm
DOM0_SRPMS += $(PYCRYPTO_SOURCE)


.PHONY: build
build: $(XSCONTAINER_STAMP) $(SUPP_PACK)

.PHONY: $(XSCONTAINER_STAMP)
$(XSCONTAINER_STAMP): $(MY_SOURCES)/MANIFEST
	mkdir -p $(RPM_SRPMSDIR) $(RPM_SOURCESDIR) $(RPM_RPMSDIR) $(MY_OUTPUT_DIR)\
		$(MY_MAIN_PACKAGES)
	cd $(REPO) && \
	    git archive --format=tar --prefix=xscontainer-$(PLATFORM_VERSION)/ HEAD\
        | bzip2 > $(RPM_SOURCESDIR)/xscontainer-$(COMPLETE_VERSION).tar.bz2
	REPO=$(REPO) MY_OUTPUT_DIR=$(MY_OUTPUT_DIR) RELEASE=$(RELEASE) \
		VERSION=$(VERSION) $(MAKE) -C $(REPO) bdist_rpm
	touch $@

.PHONY: $(MY_SOURCES)/MANIFEST
$(MY_SOURCES)/MANIFEST: $(MY_SOURCES_DIRSTAMP)
	rm -f $@
	/bin/sh ./srpms-to-manifest xscontainer $(MY_OUTPUT_DIR)/SRPMS > $@

.PHONY: clean
clean:
	rm -f $(OUTPUT)
	$(MAKE) -C $(REPO) clean

.PHONY: $(MY_SOURCES)/dependencies
$(MY_SOURCES)/dependencies:
	# Paramiko can be build straight away
	rpmbuild --rebuild $(PARAMIKO_SOURCE)
	# GMP needs the nomd5-workaround as it is from el7
	rpm -i $(GMP_SOURCE) --nomd5
	rpmbuild -bs /usr/src/redhat/SPECS/$(GMP_NAME).spec
	rpmbuild --rebuild  /usr/src/redhat/SRPMS/$(GMP_FULLNAME).src.rpm
	# Extract GMP for compiling pycrypto - avoid installing inside the build system
	mkdir -p /usr/src/redhat/BUILD/gmp-root
	(cd /usr/src/redhat/BUILD/gmp-root && rpm2cpio /usr/src/redhat/RPMS/x86_64/gmp-devel-5.1.1-5.x86_64.rpm | cpio -idmv)
	(cd /usr/src/redhat/BUILD/gmp-root && rpm2cpio /usr/src/redhat/RPMS/x86_64/gmp-5.1.1-5.x86_64.rpm | cpio -idmv)
	# pycrypto needs the nomd5-workaround as it is from el7
	rpm -i $(PYCRYPTO_SOURCE) --nomd5
	# patch pycrypto to use the gmp extracted in the above
	patch -d / -p1 < python-crypto-gmp-version-workaround.patch
	rpmbuild -bs /usr/src/redhat/SPECS/$(PYCRYPTO_NAME).spec --nodeps
	rpmbuild --rebuild /usr/src/redhat/SRPMS/$(PYCRYPTO_FULLNAME).src.rpm --nodeps
	touch $@

.PHONY: $(SUPP_PACK)
$(SUPP_PACK): $(XSCONTAINER_STAMP) $(MY_SOURCES)/dependencies
	mkdir -p $(MY_OBJ_DIR)/ISO-SOURCES
	cp -f $(MY_OUTPUT_DIR)/$(SRPM) $(MY_OBJ_DIR)/ISO-SOURCES/
	cp -f $(DOM0_SRPMS) $(MY_OBJ_DIR)/ISO-SOURCES/
	mkisofs -A "Citrix" -V "xscontainer" -J -joliet-long -r -o $(SUPP_PACK_SOURCES) $(MY_OBJ_DIR)/ISO-SOURCES
	./make-supp-pack --out $(dir $@) \
	                 --pdn $(PRODUCT_BRAND) \
	                 --pdv $(COMPLETE_VERSION) \
	                 --bld $(RELEASE) \
	                 --spn xscontainer \
	                 --spd "XenServer Container Management" \
	                 --rxv "6.5" \
	                 $(MY_OUTPUT_DIR)/$(RPM) \
	                 $(DOM0_RPMS)
	mv $(dir $@)/xscontainer.iso $@.iso
	mv $(dir $@)/xscontainer.iso.md5 $@.iso.md5
