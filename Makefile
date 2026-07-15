# 常用命令封装。跑 `make help` 看所有命令。

.PHONY: help install install-dev init-db lint format test clean update features quality select report pipeline schedule

help:
	@echo "install       安装运行依赖"
	@echo "install-dev   安装开发依赖"
	@echo "init-db       初始化数据库"
	@echo "lint          代码检查（ruff + mypy）"
	@echo "format        格式化代码（ruff format）"
	@echo "test          跑测试"
	@echo "pipeline      端到端跑一遍：拉数→特征→质量→选股→日报"
	@echo "schedule      启动调度器"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

init-db:
	python -m quant_system.cli init-db

lint:
	ruff check quant_system
	mypy quant_system

format:
	ruff format quant_system
	ruff check --fix quant_system

test:
	pytest -v

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	rm -rf build/ dist/ *.egg-info/

update:
	python -m quant_system.cli update

features:
	python -m quant_system.cli features

quality:
	python -m quant_system.cli quality

select:
	python -m quant_system.cli select

report:
	python -m quant_system.cli report

pipeline:
	python -m quant_system.cli pipeline

schedule:
	python -m quant_system.cli schedule
