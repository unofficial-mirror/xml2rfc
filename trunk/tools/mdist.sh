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
tar cvfz ../releases/xml2rfc-$release.tgz --transform="s,^\./,xml2rfc-$release/," $files

# copy tcl to proper place, always overwriting dev version
cp xml2rfc.tcl ../website/web/etc/xml2rfc-dev.tcl

case $release in
    *dev ) 
	;;
    * )
        # copy tcl to proper place, overwriting production version
	cp xml2rfc.tcl ../website/web/etc/xml2rfc.tcl

	# copy just created .tgz version of release into an website/web/authoring .tgz version
	cp ../releases/xml2rfc-$release.tgz ../website/web/authoring/xml2rfc-$release.tgz

	# rest of the work is done in website/web/authoring
	cd ../website/web/authoring

	# unpack .tgz file
	tar xzf xml2rfc-$release.tgz

	# create .zip file
	zip -r xml2rfc-$release.zip xml2rfc-$release

	# copy all top level files here
	cp xml2rfc-$release/* .

	# update xml2rfc.tgz and xml2rfc.zip
	cp -f xml2rfc-$release.tgz xml2rfc.tgz
	cp -f xml2rfc-$release.zip xml2rfc.zip

	# add the new files and directories to svn
	svn add xml2rfc-$release.tgz
	svn add xml2rfc-$release.zip
	svn add xml2rfc-$release

	# commit everything into svn
	echo Now you need to run
	echo cd ..
	echo svn commit -m "'release $release'"
	;;
esac
