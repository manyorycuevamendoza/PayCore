#!/usr/bin/env bash
# Compila el informe técnico y deja el PDF con su nombre definitivo.
#
# Requisitos: TeX Live con tikz, biblatex y booktabs. La bibliografía usa el
# backend bibtex porque biber no está instalado en el entorno de desarrollo
# del proyecto; si dispones de biber, cambia backend=bibtex en main.tex.
set -euo pipefail
cd "$(dirname "$0")"

latexmk -pdf -interaction=nonstopmode main.tex
cp main.pdf ../PayCore_Technical_Report.pdf
echo
echo "Informe en docs/PayCore_Technical_Report.pdf ($(pdfinfo main.pdf | awk '/Pages/{print $2}') páginas)"
