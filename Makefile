#Run precommit hook linting
lint:
	pre-commit run --all-files

#Run ufmt across entire repo
lint_all:
	find . -path ./venv -prune -o -name "*.py" -exec ufmt check {} +

#Format code using ufmt
format:
	find . -path ./venv -prune -o -name "*.py" -exec ufmt format {} +
