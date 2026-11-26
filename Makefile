VERSION := $(shell python3 -c "import halcyon;print(halcyon.__version__)")
TARBALL := dist/halcyon-$(VERSION).tar.gz

.PHONY: test doctor sdist rpm firmware clean

test:
	python3 -m pytest -q tests

doctor:
	python3 -m halcyon doctor

sdist:
	mkdir -p dist
	git archive --format=tar.gz --prefix=halcyon-$(VERSION)/ -o $(TARBALL) HEAD

rpm: sdist
	rpmbuild -ba packaging/halcyon.spec --define "_sourcedir $(CURDIR)/dist" --define "_topdir $(CURDIR)/dist/rpmbuild"

firmware:
	cmake -S firmware/rp2350-diag -B firmware/rp2350-diag/build
	cmake --build firmware/rp2350-diag/build -j
	@echo "UF2: firmware/rp2350-diag/build/halcyon_diag.uf2 (hold BOOT, plug in, copy to RP2350 drive)"

clean:
	rm -rf dist firmware/rp2350-diag/build work .pytest_cache
