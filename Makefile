.PHONY: docs

docs:
	quarto render USAGE.qmd --to gfm --output USAGE.md
