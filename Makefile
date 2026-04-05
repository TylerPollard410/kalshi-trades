.PHONY: docs

docs:
	quarto render USAGE.qmd --to gfm --output USAGE.md
	quarto render USAGE.qmd --to gfm --output USAGE-gfm.md
