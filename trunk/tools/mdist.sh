#!/bin/sh

if [ $# -ne 1 ]
then echo Usage: $0 release-number 1>&2
    exit 1
fi

release=$1

# update release number in xml2rfc.tcl
ed xml2rfc.tcl <<EOF
	H
	/^set prog_version/s/".*"/"v$release"/
	w
	q
EOF

# create the .tgz version of the release into releases directory
files=$(find . -name .svn -prune -o -name tools -prune -o -type f -print)

# copy tcl and README to proper place, always overwriting dev version
cp xml2rfc.tcl ../website/etc/xml2rfc-dev.tcl
cp README.html ../website/web/authoring/README-dev.html

case $release in
    *dev ) 

	TMPAREA=/var/tmp/xml2rfc-mdist-$$
	mkdir $TMPAREA
	tar cvfz $TMPAREA/xml2rfc-$release.tgz --transform="s,^\./,xml2rfc-$release/," $files

	(
	   cd $TMPAREA
	   # unpack .tgz file
	   tar xzf xml2rfc-$release.tgz

	   # create .zip file
	   zip -r xml2rfc-$release.zip xml2rfc-$release
	)

	cp $TMPAREA/xml2rfc-$release.tgz ../website/web/authoring/xml2rfc-dev.tgz
	cp $TMPAREA/xml2rfc-$release.zip ../website/web/authoring/xml2rfc-dev.zip
	rm -rf $TMPAREA

	;;

    * )
        # copy tcl to proper place, overwriting production version
	cp xml2rfc.tcl ../website/etc/xml2rfc.tcl

	# create the .tgz file
	tar cvfz ../releases/xml2rfc-$release.tgz --transform="s,^\./,xml2rfc-$release/," $files

	# copy just created .tgz version of release into an website/web/authoring .tgz version
	cp ../releases/xml2rfc-$release.tgz ../website/web/authoring/xml2rfc-$release.tgz

	# rest of the work is done in website/web/authoring
	cd ../website/web/authoring

	# unpack .tgz file
	tar xzf xml2rfc-$release.tgz

	# create .zip file
	rm -f xml2rfc-$release.zip
	zip -r xml2rfc-$release.zip xml2rfc-$release

	# copy all top level files here
	cp -r xml2rfc-$release/* .

	# update xml2rfc.tgz and xml2rfc.zip
	cp -f xml2rfc-$release.tgz xml2rfc.tgz
	cp -f xml2rfc-$release.zip xml2rfc.zip

	# always overwrite the dev versions
        cp xml2rfc-$release.zip xml2rfc-dev.zip
        cp xml2rfc-$release.tgz xml2rfc-dev.tgz

	# add the new files and directories to svn
	svn add xml2rfc-$release.tgz
	svn add xml2rfc-$release.zip
	svn add xml2rfc-$release
	;;
esac

# commit everything into svn
echo Now you need to run
echo cd ..
echo svn commit -m "'release $release'"
