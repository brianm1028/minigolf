# Minigolf Tournament Administrative Web Application

A comprehensive web-based administrative interface for managing minigolf tournaments built with Dash and Bootstrap.

## Features

### 🏆 Tournament Management
- **Entity Management**: Full CRUD operations for all tournament entities (Players, Teams, Tournaments, Courses, Holes, etc.)
- **Tournament Control**: Start/stop tournaments and update leaderboards on demand
- **Team Management**: Drag-and-drop interface for assigning players to teams

### 📊 Real-time Monitoring
- **Live Leaderboards**: Team and player rankings with configurable auto-refresh (5s to 5min intervals)
- **Manual Updates**: On-demand leaderboard updates with single button click
- **Tournament Status**: Real-time tournament state monitoring

### 📄 Card & Document Generation
- **Team Cards**: Generate 8.5" x 5.5" printable PDF team cards with QR codes
- **Hole Cards**: Generate 8.5" x 5.5" printable PDF hole cards with QR codes
- **Scorecards**: Generate and email PDF scorecards to team members
- **QR Code Integration**: All cards include scannable QR codes with embedded data

### 📱 Scorecard Management
- **Digital Scorecards**: View current scores in minigolf-style format
- **Course Information**: Display hole names, par values, and current scores
- **PDF Generation**: Create printable scorecards for teams
- **Email Distribution**: Automatically email scorecards to team members

## Prerequisites

- Python 3.12.7+
- Neo4j Database running on `bolt://localhost:7687`
- Main API service running on port 8000 (main.py)
- Tournament API service running on port 8000/tournament (mounted)
- Gmail account for email functionality (optional)

## Installation

1. Install dependencies:
