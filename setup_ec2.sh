#!/bin/bash
set -e

echo "=== AWS EC2 TRADING AGENT SETUP ==="

# 1. Update system & install git
sudo apt-get update -y
sudo apt-get install -y git curl python3-pip

# 2. Install uv package manager
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env

# 3. Enable & start systemd service
sudo cp trading_agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable trading_agent
sudo systemctl start trading_agent

echo "=== DEPLOYMENT COMPLETE ==="
echo "Status: sudo systemctl status trading_agent"
echo "Logs  : journalctl -u trading_agent -f"
