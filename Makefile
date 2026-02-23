# Makefile for Agent Company Swarm container management

# Variables
DC=docker compose
PROFILE=--profile full

.PHONY: help start stop restart status upgrade clean logs up

# Default target
help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  start     Start all services (production mode)"
	@echo "  stop      Stop all services"
	@echo "  restart   Restart all services"
	@echo "  status    Show status of all containers"
	@echo "  upgrade   Rebuild and restart all services"
	@echo "  logs      Follow logs for all services"
	@echo "  clean     Remove all containers, networks, and volumes"
	@echo "  dev       Start in development mode with hot reload"

# Start services
start:
	$(DC) $(PROFILE) up -d

# Stop services
stop:
	$(DC) $(PROFILE) stop

# Restart services
restart:
	$(DC) $(PROFILE) restart

# Show status
status:
	$(DC) $(PROFILE) ps

# Upgrade/Rebuild/Restart
upgrade:
	$(DC) $(PROFILE) up -d --build

# Follow logs
logs:
	$(DC) $(PROFILE) logs -f

# Complete cleanup
clean:
	$(DC) $(PROFILE) down --volumes --remove-orphans

# Shortcuts
up: start

# Development mode
dev:
	$(DC) --profile dev up
