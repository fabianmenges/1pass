build: clean
	python setup.py sdist

pex:
	pex --disable-cache . -m onepassword -o 1pass 

clean:
	rm -f 1pass
	rm -rf dist/*
	rm -rf 1pass.egg-info
