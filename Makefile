.PHONY: help run build up down restart logs clean \
        backend jupyter logs-backend logs-jupyter \
        restart-backend restart-jupyter rebuild-jupyter eval

COMPOSE ?= docker compose

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# --- Full stack ------------------------------------------------------------
run: up ## Alias for `up`

up: ## Build + start the full stack (backend:1019, jupyter:8020)
	$(COMPOSE) up --build -d
	@echo "backend -> http://localhost:1019/v1/hello/hello_world"
	@echo "jupyter -> http://localhost:8020/?token=vb"

build: ## Build all images
	$(COMPOSE) build

down: ## Stop the stack
	$(COMPOSE) down

restart: ## Restart the whole stack
	$(COMPOSE) restart

logs: ## Tail logs for all services
	$(COMPOSE) logs -f

clean: ## Stop and remove containers, volumes, and locally-built images
	$(COMPOSE) down -v --rmi local

# --- Backend ---------------------------------------------------------------
backend: ## Build + start only the backend
	$(COMPOSE) up --build -d backend

logs-backend: ## Tail backend logs
	$(COMPOSE) logs -f backend

restart-backend: ## Restart the backend
	$(COMPOSE) restart backend

eval: ## Run the eval harness (Phase 11); pass flags via ARGS="--dry-run …"
	$(COMPOSE) exec backend python -m api.eval_harness $(ARGS)

# --- Jupyter ---------------------------------------------------------------
jupyter: ## Build + start only jupyter
	$(COMPOSE) up --build -d jupyter

logs-jupyter: ## Tail jupyter logs
	$(COMPOSE) logs -f jupyter

restart-jupyter: ## Restart jupyter
	$(COMPOSE) restart jupyter

# Force a clean rebuild of the jupyter image: pull the latest base (quay.io
# scipy-notebook, Ubuntu 24.04 / glibc >= 2.36) and rebuild without cache.
rebuild-jupyter: ## No-cache rebuild of the jupyter image (use after Dockerfile base changes)
	$(COMPOSE) build --no-cache --pull jupyter
	$(COMPOSE) up -d jupyter

copy-skills:
	rm -rf .claude/skills
	mkdir -p .claude/skills
	cp -R skills/. .claude/skills/
	if [ -d optional_skills ]; then cp -R optional_skills/. .claude/skills/; fi
	@echo "Copied skill(s) to .claude/skills/"
	rm -rf .agents/skills
	mkdir -p .agents/skills
	cp -R skills/. .agents/skills/
	if [ -d optional_skills ]; then cp -R optional_skills/. .agents/skills/; fi
	@echo "Copied skill(s) to .agents/skills/"