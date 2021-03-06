#!/bin/bash
# Usage: make.sh latex|sphinx

name=ftut
version=1.0
version=1.1

set -x

function system {
  "$@"
  if [ $? -ne 0 ]; then
    echo "make.sh: unsuccessful command $@"
    echo "abort!"
    exit 1
  fi
}

# We have Norwegian characters in the acknowledgement and this
# requires latin1 for latex and utf-8 for rst/sphinx

# Make latex
system preprocess -DFORMAT=pdflatex newcommands.p.tex > newcommands.tex
system doconce format pdflatex $name --device=paper --latex_title_layout=titlepage "--latex_code_style=default:vrb-blue1@sys:vrb[frame=lines,label=\\fbox{{\tiny Terminal}},framesep=2.5mm,framerule=0.7pt,fontsize=\fontsize{9pt}{9pt}]" --encoding=utf-8 --latex_copyright=titlepages --skip_inline_comments

#doconce replace 'ptex2tex}' 'ptex2tex,subfigure}' $name.p.tex
#doconce subst 'This document presents a' '\\tableofcontents\n\n\\clearpage\n\nThis document presents a' $name.p.tex
system pdflatex $name
system bibtex $name
system makeindex $name
pdflatex $name
pdflatex $name
cp $name.pdf fenics-tutorial-4print.pdf

# Make sphinx
preprocess -DFORMAT=html newcommands.p.tex > newcommands.tex
dir=sphinx-rootdir
system doconce format sphinx $name --encoding=utf-8 --skip_inline_comments
system doconce split_rst $name.rst
system doconce sphinx_dir dirname=$dir version=$version theme=fenics $name
system python automake_sphinx.py

# Make Bootstrap HTML
system doconce format html $name --encoding=utf-8 --html_style=bootswatch_journal --skip_inline_comments
system doconce split_html $name.html --pagination

dest=../pub
rm -rf $dest/sphinx
cp -r fenics-tutorial-4print.pdf sphinx-rootdir/_build/html $dest
mv -f $dest/html $dest/sphinx
cp -r $name.html ._*.html fig $dest
