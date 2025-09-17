from fastapi import FastAPI, HTTPException, Response
from neo4j import GraphDatabase
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import logging
from contextlib import contextmanager
import qrcode
import io
import base64
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(title="Minigolf Tournament Application API", version="1.0.0")

# Neo4j connection settings
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "minigolf"
NEO4J_DATABASE = "minigolf"

# Neo4j driver
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

@contextmanager
def get_db_session():
    """Context manager for Neo4j database sessions"""
    session = driver.session(database=NEO4J_DATABASE)
    try:
        yield session
    finally:
        session.close()

# Pydantic Models
class RecordScoreRequest(BaseModel):
    player_number: int
    tournament_name: str
    course_name: str
    hole_number: int
    score: int

class TeamLeaderboardEntry(BaseModel):
    team_name: str
    team_number: int
    total: int
    average: float
    rank: int
    holes_played: int
    current_hole: int
    starting_hole: int
    completed: bool

class PlayerLeaderboardEntry(BaseModel):
    player_name: str
    player_number: int
    total: int
    average: float
    rank: int
    holes_played: int
    current_hole: int
    starting_hole: int
    completed: bool

class LeaderboardResponse(BaseModel):
    message: str
    updated_player_rounds: int
    updated_team_rounds: int

class EndPlayerRoundRequest(BaseModel):
    player_number: int
    tournament_name: str

class EndTeamRoundRequest(BaseModel):
    team_number: int
    tournament_name: str

class EndRoundResponse(BaseModel):
    message: str
    total: int
    average: float
    holes_played: int

class EndTournamentRequest(BaseModel):
    tournament_name: str

class StartTournamentRequest(BaseModel):
    tournament_name: str

class ActivateTeamRoundRequest(BaseModel):
    tournament_name: str
    team_number: int
    course_name: str
    hole_number: int

class ActivatePlayerRoundRequest(BaseModel):
    tournament_name: str
    team_number: int
    player_number: int
    course_name: str
    hole_number: int

class TournamentManagementResponse(BaseModel):
    message: str
    affected_count: int

class RecordTeamScoresRequest(BaseModel):
    tournament_name: str
    course_name: str
    hole_number: int
    team_number: int
    player_scores: list[dict]  # [{"player_number": int, "score": int}]

class GenerateTeamCardRequest(BaseModel):
    team_number: int

class GenerateHoleCardRequest(BaseModel):
    course_name: str
    hole_number: int

class QRCodeResponse(BaseModel):
    message: str
    qr_code_base64: str
    encoded_data: Dict[str, Any]

class CurrentTeamHoleRequest(BaseModel):
    tournament_name: str
    team_number: int

class PlayerScoreCardRequest(BaseModel):
    tournament_name: str
    player_number: int

# Application Layer Endpoints

@app.post("/update-leaderboard", response_model=LeaderboardResponse)
async def update_leaderboard():
    """
    Calculates the total and average scores for each PlayerRound and TeamRound 
    based on the scores of the PLAYED_HOLE relationships. 
    Calculates the player and team ranks by comparing the total scores.
    """
    try:
        with get_db_session() as session:
            # Update PlayerRound totals and averages
            player_update_query = """
            MATCH (pr:PlayerRound)-[ph:PLAYED_HOLE]->(h:Hole)
            WHERE pr.status IN ['active','complete']
            WITH pr, collect(ph.score) as scores
            SET pr.total = reduce(sum = 0, score IN scores | sum + score),
                pr.average = reduce(sum = 0, score IN scores | sum + score) * 1.0 / size(scores)
            RETURN count(pr) as updated_players
            """
            player_result = session.run(player_update_query)
            updated_players = player_result.single()["updated_players"]

            # Update PlayerRound ranks
            player_rank_query = """
            MATCH (pr:PlayerRound)
            WHERE pr.status IN ['active','complete'] AND pr.total IS NOT NULL
            WITH pr ORDER BY pr.total ASC
            WITH collect(pr) as player_rounds
            UNWIND range(0, size(player_rounds)-1) as i
            WITH player_rounds[i] as pr, i+1 as rank
            SET pr.rank = rank
            """
            session.run(player_rank_query)

            # Update TeamRound totals and averages based on PlayerRounds
            team_update_query = """
            MATCH (t:Team)-[:PLAYED_ROUND]->(tr:TeamRound)
            WHERE tr.status IN ['active','complete']
            MATCH (p:Player)-[:MEMBER_OF]->(t)
            MATCH (p)-[:PLAYED_ROUND]->(pr:PlayerRound)
            WHERE pr.status IN ['active','complete'] AND pr.total IS NOT NULL
            MATCH (pr)-[:PLAYED_ROUND]->(tr)
            WITH tr, collect(pr.total) as player_totals
            SET tr.total = reduce(sum = 0, total IN player_totals | sum + total),
                tr.average = reduce(sum = 0, total IN player_totals | sum + total) * 1.0 / size(player_totals)
            RETURN count(tr) as updated_teams
            """
            team_result = session.run(team_update_query)
            updated_teams = team_result.single()["updated_teams"]

            # Update TeamRound ranks
            team_rank_query = """
            MATCH (tr:TeamRound)
            WHERE tr.status IN ['active','complete'] AND tr.average IS NOT NULL
            WITH tr ORDER BY tr.average ASC
            WITH collect(tr) as team_rounds
            UNWIND range(0, size(team_rounds)-1) as i
            WITH team_rounds[i] as tr, i+1 as rank
            SET tr.rank = rank
            """
            session.run(team_rank_query)

            return LeaderboardResponse(
                message="Leaderboard updated successfully",
                updated_player_rounds=updated_players,
                updated_team_rounds=updated_teams
            )

    except Exception as e:
        logger.error(f"Error updating leaderboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/record-score")
async def record_score(request: RecordScoreRequest):
    """
    Takes a player number, course name, hole number, and score as input.
    Identifies the active PlayerRound for the given player, course, and hole
    and creates or updates the PLAYED_HOLE relationship. After recording the score,
    updates the CURRENT_HOLE relationship to point to the next hole.
    """
    try:
        with get_db_session() as session:
            # Record the score
            upsert_query = """
            MATCH (p:Player {number: $player_number})-[:PLAYED_ROUND]->(pr:PlayerRound)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t:Tournament {name:$tournament_name})
            MATCH (pr)-[:PLAYED_ON]->(c:Course {name: $course_name})-[:HAS_HOLE]->(h:Hole {number: $hole_number})
            WHERE pr.status = 'active'
            MERGE (pr)-[prh:PLAYED_HOLE]->(h)
            SET prh.score = $score
            WITH pr, c, h, prh
            MATCH (pr)-[:STARTING_HOLE]->(sh:Hole)
            MATCH (c)-[:HAS_HOLE]->(nh:Hole)
            WHERE nh.number = CASE
                WHEN h.number = sh.number THEN 18
                WHEN h.number = 17 THEN 1
                ELSE h.number + 1
            END
            WITH pr, nh, prh, sh
            OPTIONAL MATCH (pr)-[ch:CURRENT_HOLE]->(h)
            DELETE ch
            WITH pr, nh, sh, prh
            FOREACH (dummy IN CASE WHEN nh is null THEN [1] ELSE [] END | SET pr.status = 'complete')
            FOREACH (dummy IN CASE WHEN nh is not null THEN [1] ELSE [] END | CREATE (pr)-[:CURRENT_HOLE]->(nh))
            WITH pr, nh, sh, prh
            RETURN 
            CASE WHEN nh is null THEN 'complete' ELSE 'active' END as status,
            prh.score as recorded_score,
            CASE WHEN nh is null THEN 0 ELSE nh.number END as next_hole
            """

            upsert_result = session.run(upsert_query,
                                        player_number=request.player_number,
                                        course_name=request.course_name,
                                        tournament_name=request.tournament_name,
                                        hole_number=request.hole_number,
                                        score=request.score)
            record = upsert_result.data()[0]
            print(record)

            return {
                "message": "Score recorded successfully",
                "player_number": request.player_number,
                "course_name": request.course_name,
                "hole_number": request.hole_number,
                "score": record["recorded_score"],
                "next_hole": record["next_hole"]
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording score: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/team-leaderboard/{tournament_name}", response_model=List[TeamLeaderboardEntry])
async def get_team_leaderboard(tournament_name: str):
    """
    Given a Tournament name, returns the Team name, total, average, and rank values
    and the number of holes played for the active TeamRound in that Tournament,
    ordered by rank descending.
    """
    try:
        with get_db_session() as session:
            query = """
            MATCH (t:Tournament {name: $tournament_name, active: true})-[:HAS_TEAM]->(team:Team)
            MATCH (team)-[:PLAYED_ROUND]->(tr:TeamRound) WHERE tr.status IN ['active','complete']
            MATCH (tr)-[:IN_TOURNAMENT]->(t)
            OPTIONAL MATCH (team)<-[:MEMBER_OF]-(p:Player)-[:PLAYED_ROUND]->(pr:PlayerRound) WHERE pr.status IN ['active','complete']
            OPTIONAL MATCH (pr)-[:PLAYED_ROUND]->(tr)
            OPTIONAL MATCH (pr)-[ph:PLAYED_HOLE]->(h:Hole)
            OPTIONAL MATCH (tr)-[:STARTING_HOLE]->(sh:Hole)
            OPTIONAL MATCH (tr)-[:CURRENT_HOLE]->(ch:Hole)
            WITH team, tr, count(DISTINCT h) as holes_played, sh, ch
            WHERE tr.total IS NOT NULL AND tr.average IS NOT NULL AND tr.rank IS NOT NULL
            RETURN team.name as team_name, 
                team.number as team_number,
                   tr.total as total, 
                   tr.average as average, 
                   tr.rank as rank,
                   holes_played,
                   CASE WHEN ch IS NOT NULL THEN ch.number ELSE 0 END as current_hole,
                   CASE WHEN sh IS NOT NULL THEN sh.number ELSE 0 END as starting_hole,                   
                   CASE WHEN tr.completed IS NOT NULL THEN tr.completed ELSE False END as completed
            ORDER BY tr.rank DESC
            """

            result = session.run(query, tournament_name=tournament_name)

            leaderboard = []
            for record in result:
                leaderboard.append(TeamLeaderboardEntry(
                    team_name=record["team_name"],
                    team_number=record["team_number"],
                    total=record["total"],
                    average=record["average"],
                    rank=record["rank"],
                    holes_played=record["holes_played"],
                    current_hole=record["current_hole"],
                    starting_hole=record["starting_hole"],
                    completed=record["completed"]
                ))

            return leaderboard

    except Exception as e:
        logger.error(f"Error getting team leaderboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/player-leaderboard/{tournament_name}", response_model=List[PlayerLeaderboardEntry])
async def get_player_leaderboard(tournament_name: str):
    """
    Given a Tournament name, returns the Player name, total, average, and rank values
    and the number of holes played for the active PlayerRound in that Tournament,
    ordered by rank descending.
    """
    try:
        with get_db_session() as session:
            query = """
            MATCH (t:Tournament {name: $tournament_name, active: true})-[:HAS_TEAM]->(team:Team)
            MATCH (team)<-[:MEMBER_OF]-(p:Player)-[:PLAYED_ROUND]->(pr:PlayerRound) WHERE pr.status IN ['active','complete']
            MATCH (pr)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t) WHERE tr.status IN ['active','complete']
            OPTIONAL MATCH (pr)-[ph:PLAYED_HOLE]->(h:Hole)
            OPTIONAL MATCH (pr)-[:CURRENT_HOLE]->(ch:Hole)
            OPTIONAL MATCH (pr)-[:STARTING_HOLE]->(sh:Hole)
            WITH p, pr, ch, sh, count(h) as holes_played
            WHERE pr.total IS NOT NULL AND pr.average IS NOT NULL AND pr.rank IS NOT NULL
            RETURN p.name as player_name,
                    p.number as player_number,
                   pr.total as total,
                   pr.average as average,
                   pr.rank as rank,
                   holes_played,
                   CASE WHEN ch IS NOT NULL THEN ch.number ELSE 0 END as current_hole,
                   CASE WHEN sh IS NOT NULL THEN sh.number ELSE 0 END as starting_hole,
                   CASE WHEN pr.completed IS NOT NULL THEN pr.completed ELSE False END as completed
            ORDER BY pr.rank DESC
            """

            result = session.run(query, tournament_name=tournament_name)

            leaderboard = []
            for record in result:
                leaderboard.append(PlayerLeaderboardEntry(
                    player_name=record["player_name"],
                    player_number=record["player_number"],
                    total=record["total"],
                    average=record["average"],
                    rank=record["rank"],
                    holes_played=record["holes_played"],
                    current_hole=record["current_hole"],
                    starting_hole=record["starting_hole"],
                    completed=record["completed"]
                ))

            return leaderboard

    except Exception as e:
        logger.error(f"Error getting player leaderboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/end-player-round", response_model=EndRoundResponse)
async def end_player_round(request: EndPlayerRoundRequest):
    """
    Marks a PlayerRound as inactive and runs a final calculation 
    of the player's total and average scores.
    """
    try:
        with get_db_session() as session:
            # Find and validate the active PlayerRound
            find_query = """
            MATCH (p:Player {number: $player_number})-[:PLAYED_ROUND]->(pr:PlayerRound {active: true})
            MATCH (pr)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t:Tournament {name: $tournament_name})
            RETURN elementId(pr) as player_round_id, pr.total as current_total, pr.average as current_average
            """

            find_result = session.run(find_query, 
                                    player_number=request.player_number,
                                    tournament_name=request.tournament_name)
            find_record = find_result.single()

            if not find_record:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Active PlayerRound not found for player {request.player_number} in tournament {request.tournament_name}"
                )

            player_round_id = find_record["player_round_id"]

            # Calculate final scores and mark as inactive
            final_calc_query = """
            MATCH (pr:PlayerRound) WHERE elementId(pr) = $player_round_id
            OPTIONAL MATCH (pr)-[ph:PLAYED_HOLE]->(h:Hole)
            WITH pr, collect(ph.score) as scores
            SET pr.active = false, pr.completed = true,
                pr.total = CASE 
                    WHEN size(scores) > 0 THEN reduce(sum = 0, score IN scores | sum + score)
                    ELSE 0
                END,
                pr.average = CASE 
                    WHEN size(scores) > 0 THEN reduce(sum = 0, score IN scores | sum + score) * 1.0 / size(scores)
                    ELSE 0.0
                END
            RETURN pr.total as total, pr.average as average, size(scores) as holes_played
            """

            calc_result = session.run(final_calc_query, player_round_id=player_round_id)
            calc_record = calc_result.single()

            return EndRoundResponse(
                message=f"Player round ended successfully for player {request.player_number}",
                total=calc_record["total"],
                average=calc_record["average"],
                holes_played=calc_record["holes_played"]
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ending player round: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/end-team-round", response_model=EndRoundResponse)
async def end_team_round(request: EndTeamRoundRequest):
    """
    Marks a TeamRound as inactive and runs a final calculation 
    of the team's total and average scores.
    """
    try:
        with get_db_session() as session:
            # Find and validate the active TeamRound
            find_query = """
            MATCH (team:Team {number: $team_number})-[:PLAYED_ROUND]->(tr:TeamRound {active: true})
            MATCH (tr)-[:IN_TOURNAMENT]->(t:Tournament {name: $tournament_name})
            RETURN elementId(tr) as team_round_id, tr.total as current_total, tr.average as current_average
            """

            find_result = session.run(find_query,
                                    team_number=request.team_number,
                                    tournament_name=request.tournament_name)
            find_record = find_result.single()

            if not find_record:
                raise HTTPException(
                    status_code=404,
                    detail=f"Active TeamRound not found for team {request.team_number} in tournament {request.tournament_name}"
                )

            team_round_id = find_record["team_round_id"]

            # Calculate final scores based on associated PlayerRounds and mark as inactive
            final_calc_query = """
            MATCH (tr:TeamRound) WHERE elementId(tr) = $team_round_id
            MATCH (team:Team)-[:PLAYED_ROUND]->(tr)
            OPTIONAL MATCH (p:Player)-[:MEMBER_OF]->(team)
            OPTIONAL MATCH (p)-[:PLAYED_ROUND]->(pr:PlayerRound)
            OPTIONAL MATCH (pr)-[:PLAYED_ROUND]->(tr)
            OPTIONAL MATCH (pr)-[ph:PLAYED_HOLE]->(h:Hole)
            WITH tr, pr, collect(ph.score) as player_scores
            WITH tr, collect(CASE 
                WHEN size(player_scores) > 0 
                THEN reduce(sum = 0, score IN player_scores | sum + score)
                ELSE 0
            END) as player_totals
            WITH tr, player_totals, 
                 reduce(holes = 0, pt IN player_totals | 
                    CASE WHEN pt > 0 THEN holes + (pt / 3) ELSE holes END) as total_holes
            SET tr.active = false, tr.completed = true,
                tr.total = reduce(sum = 0, total IN player_totals | sum + total),
                tr.average = CASE 
                    WHEN size(player_totals) > 0 AND reduce(sum = 0, total IN player_totals | sum + total) > 0
                    THEN reduce(sum = 0, total IN player_totals | sum + total) * 1.0 / size(player_totals)
                    ELSE 0.0
                END
            RETURN tr.total as total, tr.average as average, size(player_totals) as holes_played
            """

            calc_result = session.run(final_calc_query, team_round_id=team_round_id)
            calc_record = calc_result.single()

            return EndRoundResponse(
                message=f"Team round ended successfully for team {request.team_number}",
                total=calc_record["total"],
                average=calc_record["average"], 
                holes_played=calc_record["holes_played"]
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ending team round: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/activate-player-round", response_model=TournamentManagementResponse)
async def activate_player_round(request: ActivatePlayerRoundRequest):
    """
    Given a Tournament name, Team, and Player, updates all PlayerRounds related 
    to that team round as active and resets their total, average, and rank values to 0.
    """
    try:
        with get_db_session() as session:
            # Find and activate PlayerRounds for the specific player in the team/tournament
            activate_query = """
            MATCH (t:Tournament {name: $tournament_name})-[:HAS_TEAM]->(team:Team {number: $team_number})
            MATCH (p:Player {number: $player_number})-[:MEMBER_OF]->(team)
            MATCH (team)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t)
            MATCH (p)-[:PLAYED_ROUND]->(pr:PlayerRound)-[:PLAYED_ROUND]->(tr)
            MATCH (tr)-[:PLAYED_ON]->(c:Course {name: $course_name})-[:HAS_HOLE]->(h:Hole {number: $hole_number})
            SET pr.active = true,
                pr.total = 0,
                pr.average = 0.0,
                pr.rank = 0,
                pr.status = "active",
                pr.completed = false
            WITH DISTINCT pr,h
            OPTIONAL MATCH (pr)-[prh:STARTING_HOLE|CURRENT_HOLE]->(hx:Hole)
            DELETE prh
            WITH DISTINCT pr,h
            CREATE (pr)-[:STARTING_HOLE]->(h)
            CREATE (pr)-[:CURRENT_HOLE]->(h)
            RETURN count(pr) as activated_count
            """

            result = session.run(activate_query,
                            tournament_name=request.tournament_name,
                            team_number=request.team_number,
                            player_number=request.player_number,
                            hole_number=request.hole_number,
                            course_name=request.course_name)

            activated_count = result.single()["activated_count"]

            if activated_count == 0:
                raise HTTPException(
                    status_code=404,
                    detail=f"No PlayerRounds found for player {request.player_number} in team {request.team_number} for tournament {request.tournament_name}"
                )

            return TournamentManagementResponse(
                message=f"Activated {activated_count} PlayerRound(s) for player {request.player_number}",
                affected_count=activated_count
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating player round: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/activate-team-round", response_model=TournamentManagementResponse)
async def activate_team_round(request: ActivateTeamRoundRequest):
    """
    Given a tournament name and team name, marks a TeamRound as active and resets 
    the total, average, and rank values to 0, then calls activate_player_round 
    for all PlayerRounds connected to it.
    """
    try:
        with get_db_session() as session:
            # Activate the TeamRound
            activate_team_query = """
            MATCH (t:Tournament {name: $tournament_name})-[:HAS_TEAM]->(team:Team {number: $team_number})
            MATCH (team)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t)
            MATCH (tr)-[:PLAYED_ON]->(c:Course {name: $course_name})-[:HAS_HOLE]->(h:Hole {number: $hole_number})
            SET tr.active = true,
                tr.total = 0,
                tr.average = 0.0,
                tr.rank = 0,
                tr.status = "active",
                tr.completed = false
            WITH DISTINCT tr,h
            OPTIONAL MATCH (tr)-[trh:STARTING_HOLE|CURRENT_HOLE]->(hx:Hole)
            DELETE trh
            WITH DISTINCT tr,h
            CREATE (tr)-[:STARTING_HOLE]->(h)
            CREATE (tr)-[:CURRENT_HOLE]->(h)
            RETURN count(tr) as activated_teams
            """

            team_result = session.run(activate_team_query,
                                    tournament_name=request.tournament_name,
                                    team_number=request.team_number,
                                    hole_number=request.hole_number,
                                    course_name=request.course_name)

            activated_teams = team_result.single()["activated_teams"]

            if activated_teams == 0:
                raise HTTPException(
                    status_code=404,
                    detail=f"No TeamRound found for team {request.team_number} in tournament {request.tournament_name}"
                )

            return TournamentManagementResponse(
                message=f"Activated TeamRound for {request.team_number}",
                affected_count=activated_teams
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating team round: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/record-team-scores")
async def record_team_scores(request: RecordTeamScoresRequest):
    """
    Takes a tournament name, course name, hole number, team number, and list of player scores,
    then records the score for each player and updates CURRENT_HOLE relationships.
    """
    try:
        with get_db_session() as session:
            results = []

            # Record scores for each player
            for player_score in request.player_scores:
                # Create RecordScoreRequest for individual player
                score_request = RecordScoreRequest(
                    player_number=player_score["player_number"],
                    tournament_name=request.tournament_name,
                    course_name=request.course_name,
                    hole_number=request.hole_number,
                    score=player_score["score"]
                )

                # Record the score
                await record_score(score_request)


                results.append({
                    "player_number": player_score["player_number"],
                    "score": player_score["score"]
                })

            # Update CURRENT_HOLE relationship for the team
            update_team_hole_query = """
            MATCH (te:Team {number: $team_number})-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t:Tournament {name:$tournament_name})
            MATCH (tr)-[:PLAYED_ON]->(c:Course {name: $course_name})-[:HAS_HOLE]->(h:Hole {number: $hole_number})
            WHERE tr.status = 'active'
            WITH tr, c, h
            MATCH (tr)-[:STARTING_HOLE]->(sh:Hole)
            OPTIONAL MATCH (c)-[:HAS_HOLE]->(nh:Hole)
            WHERE nh.number = CASE
                WHEN h.number = sh.number THEN 18
                WHEN h.number = 17 THEN 1
                ELSE h.number + 1
            END
            WITH tr, c, nh, sh, h
            OPTIONAL MATCH (tr)-[ch:CURRENT_HOLE]->(h)
            DELETE ch
            WITH tr, nh, sh
            FOREACH (dummy IN CASE WHEN nh is null THEN [1] ELSE [] END | SET tr.status = 'complete')
            FOREACH (dummy IN CASE WHEN nh is not null THEN [1] ELSE [] END | CREATE (tr)-[:CURRENT_HOLE]->(nh))
            WITH tr, nh, sh
            RETURN 
            CASE WHEN nh is null THEN 'complete' ELSE 'active' END as team_status,
            CASE WHEN nh is null THEN 0 ELSE nh.number END as next_hole_num

            """

            update_result = session.run(update_team_hole_query,
                       team_number=request.team_number,
                       tournament_name=request.tournament_name,
                       course_name=request.course_name,
                       hole_number=request.hole_number)

            record = update_result.data()[0]
            print(record)

            return {
                "message": f"Successfully recorded scores for team {request.team_number}",
                "tournament_name": request.tournament_name,
                "course_name": request.course_name,
                "hole_number": request.hole_number,
                "team_number": request.team_number,
                "player_results": results,
                "next_hole": record["next_hole_num"],
                "team_status": record["team_status"]
            }

    except Exception as e:
        logger.error(f"Error recording team scores: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error recording team scores: {str(e)}")


@app.post("/get-current-hole")
async def get_current_hole(request: CurrentTeamHoleRequest):
    try:
        with get_db_session() as session:
            current_hole_query = """
            MATCH (te:Team {number: $team_number})-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t:Tournament {name:$tournament_name})
            MATCH (tr)-[:PLAYED_ON]->(c:Course)
            OPTIONAL MATCH (tr)-[:CURRENT_HOLE]->(ch:Hole)
            OPTIONAL MATCH (p:Player)-[:PLAYED_ROUND]->(pr:PlayerRound)-[:PLAYED_ROUND]->(tr) WHERE pr.status = 'active'
            WITH tr, c, ch, collect(p.number) AS player_numbers
            RETURN
                CASE WHEN ch IS NOT NULL THEN ch.number ELSE 0 END as hole_number,
                CASE WHEN ch IS NOT NULL THEN ch.par ELSE 0 END as hole_par,
                CASE WHEN ch IS NOT NULL THEN ch.name ELSE '' END as hole_name,
                c.name as course_name,
                CASE WHEN size(player_numbers) > 0 THEN player_numbers ELSE 0 END as players,
                tr.status as team_status
            """

            result = session.run(current_hole_query, team_number=request.team_number, tournament_name=request.tournament_name)
            record = result.single()

            if not record:
                raise HTTPException(
                    status_code=404,
                    detail=f"No current hole found for team {request.team_number} in tournament {request.tournament_name}"
                )

            return {
                "message": f"Successfully retrieved next hole for team {request.team_number} in tournament {request.tournament_name}",
                "tournament_name": request.tournament_name,
                "course_name": record["course_name"],
                "hole_number": record["hole_number"],
                "hole_par": record["hole_par"],
                "hole_name": record["hole_name"],
                "team_number": request.team_number,
                "players": record["players"],
                "team_status": record["team_status"]
            }

    except Exception as e:
        logger.error(f"Error retrieving next hole for team: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving next hole for team: {str(e)}")

@app.post("/start-tournament", response_model=TournamentManagementResponse)
async def start_tournament(request: StartTournamentRequest):
    """
    Given a tournament name, sets all TeamRounds and PlayerRounds status to 'ready',
    deletes existing PLAYED_HOLE relationships, and resets totals, averages, and ranks to 0.
    """
    try:
        with get_db_session() as session:
            # Delete existing PLAYED_HOLE relationships and reset data
            cleanup_query = """
            MATCH (t:Tournament {name: $tournament_name})-[:HAS_TEAM]->(team:Team)
            MATCH (team)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t)
            MATCH (p:Player)-[:MEMBER_OF]->(team)
            MATCH (p)-[:PLAYED_ROUND]->(pr:PlayerRound)-[:PLAYED_ROUND]->(tr)
            OPTIONAL MATCH (pr)-[ph:PLAYED_HOLE|STARTING_HOLE|CURRENT_HOLE]->(:Hole)
            OPTIONAL MATCH (tr)-[ph:STARTING_HOLE|CURRENT_HOLE]->(:Hole)
            DELETE ph
            WITH tr, pr
            SET tr.status = 'ready',
                tr.total = 0,
                tr.average = 0.0,
                tr.rank = 0,
                pr.status = 'ready',
                pr.total = 0,
                pr.average = 0.0,
                pr.rank = 0
            RETURN count(DISTINCT tr) as updated_teams, count(DISTINCT pr) as updated_players
            """

            result = session.run(cleanup_query, tournament_name=request.tournament_name)
            record = result.single()

            if not record or (record["updated_teams"] == 0 and record["updated_players"] == 0):
                raise HTTPException(
                    status_code=404,
                    detail=f"No teams or players found for tournament {request.tournament_name}"
                )

            updated_teams = record["updated_teams"]
            updated_players = record["updated_players"]
            total_affected = updated_teams + updated_players

            return TournamentManagementResponse(
                message=f"Tournament {request.tournament_name} started with {updated_teams} teams and {updated_players} player rounds set to ready status",
                affected_count=total_affected
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting tournament: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/end-tournament", response_model=TournamentManagementResponse)
async def end_tournament(request: EndTournamentRequest):
    """
    Given a tournament name, sets all PlayerRounds and TeamRounds status to 'done' 
    and calls update_leaderboard to finalize scores and rankings.
    """
    try:
        with get_db_session() as session:
            # Set status to 'done' for all PlayerRounds and TeamRounds in the tournament
            end_tournament_query = """
            MATCH (t:Tournament {name: $tournament_name})-[:HAS_TEAM]->(team:Team)
            MATCH (team)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t)
            SET tr.status = 'done'
            WITH count(tr) as finished_teams
            MATCH (t:Tournament {name: $tournament_name})-[:HAS_TEAM]->(team:Team)
            MATCH (team)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t)
            MATCH (p:Player)-[:MEMBER_OF]->(team)
            MATCH (p)-[:PLAYED_ROUND]->(pr:PlayerRound)-[:PLAYED_ROUND]->(tr)
            SET pr.status = 'done'
            RETURN finished_teams, count(pr) as finished_players
            """

            result = session.run(end_tournament_query, tournament_name=request.tournament_name)
            record = result.single()

            if not record or (record["finished_teams"] == 0 and record["finished_players"] == 0):
                raise HTTPException(
                    status_code=404,
                    detail=f"No rounds found for tournament {request.tournament_name}"
                )

            finished_teams = record["finished_teams"]
            finished_players = record["finished_players"]

            # Temporarily set active status for final leaderboard calculation
            temp_activate_query = """
            MATCH (t:Tournament {name: $tournament_name})-[:HAS_TEAM]->(team:Team)
            MATCH (team)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t)
            MATCH (p:Player)-[:MEMBER_OF]->(team)
            MATCH (p)-[:PLAYED_ROUND]->(pr:PlayerRound)-[:PLAYED_ROUND]->(tr)
            SET pr.active = true, tr.active = true
            """
            session.run(temp_activate_query, tournament_name=request.tournament_name)

            # Perform final leaderboard calculation
            await update_leaderboard()

            # Set status back to 'done'
            session.run(end_tournament_query, tournament_name=request.tournament_name)

            total_affected = finished_teams + finished_players

            return TournamentManagementResponse(
                message=f"Tournament {request.tournament_name} ended with final leaderboard calculated. Set {finished_teams} teams and {finished_players} player rounds to done status",
                affected_count=total_affected
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ending tournament: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/get-player-scorecard")
async def get_player_scorecard(request: PlayerScoreCardRequest):
    try:
        with get_db_session() as session:
            results = []

            # Update CURRENT_HOLE relationship for the team
            get_scores_query = """
            MATCH (p:Player {number: $player_number})-[:PLAYED_ROUND]->(pr:PlayerRound)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t:Tournament {name:$tournament_name})
            MATCH (h:Hole)<-[:HAS_HOLE]-(c:Course)<-[:PLAYED_ON]-(pr)
            OPTIONAL MATCH (pr)-[prh:PLAYED_HOLE]->(h)
            RETURN
                p.name as player_name,
                h.number as hole_number,
                h.name as hole_name,
                h.par as hole_par,
                CASE WHEN prh IS NOT NULL THEN prh.score ELSE 0 END as score,
                c.name as course_name
            ORDER BY h.number ASC
            """

            result = session.run(get_scores_query,
                                 player_number=request.player_number,
                                 tournament_name=request.tournament_name
                                 )

            records = result.data()
            print(records)

            scorecard = {"player_name":"","course_name":"","scores":[{"label":"","number":0,"par":0,"value":0}]*19}
            print(scorecard)
            scorecard["scores"][0]["label"] = "Total"
            scorecard["player_name"] = records[0]["player_name"]
            scorecard["course_name"] = records[0]["course_name"]
            for score in records:
                scorecard["scores"][0]["value"]+=score["score"]
                scorecard["scores"][0]["par"]+=score["hole_par"]
                scorecard["scores"][score["hole_number"]]={"label":score["hole_name"],"number":score["hole_number"],"par":score["hole_par"],"value":score["score"]}

            print(scorecard)
            return {
                "message": f"Successfully retrieved scores for player {request.player_number}",
                "tournament_name": request.tournament_name,
                "player_number": request.player_number,
                "player_name": scorecard["player_name"],
                "course_name": scorecard["course_name"],
                "scores": scorecard["scores"]
            }

    except Exception as e:
        logger.error(f"Error retrieving player scores: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving player scores: {str(e)}")

@app.post("/generate-team-card", response_model=QRCodeResponse)
async def generate_team_card(request: GenerateTeamCardRequest):
    """
    Takes a team name and generates a QR code with the team information encoded into it.
    """
    try:
        with get_db_session() as session:
            # Get team information including players
            team_query = """
            MATCH (team:Team {number: $team_number})
            OPTIONAL MATCH (p:Player)-[:MEMBER_OF]->(team)
            OPTIONAL MATCH (team)-[:PLAYED_ROUND]->(tr:TeamRound)
            OPTIONAL MATCH (tr)-[:IN_TOURNAMENT]->(t:Tournament)
            WITH team, collect(DISTINCT {
                name: p.name,
                number: p.number,
                email: p.email
            }) as players, collect(DISTINCT {
                tournament_name: t.name,
                team_round_active: tr.active,
                total: tr.total,
                average: tr.average,
                rank: tr.rank
            }) as tournaments
            RETURN team.name as team_name,
                   team.number as team_number,
                   players,
                   tournaments
            """

            result = session.run(team_query, team_number=request.team_number)
            record = result.single()

            if not record:
                raise HTTPException(
                    status_code=404,
                    detail=f"Team {request.team_number} not found"
                )

            # Prepare team data for QR code
            team_data = {
                "type": "team_card",
                "team_name": record["team_name"],
                "team_number": record["team_number"],
                "players": [p for p in record["players"] if p["name"] is not None],
                "tournaments": [t for t in record["tournaments"] if t["tournament_name"] is not None],
                "generated_at": "2025-08-23T00:00:00Z"
            }

            # Generate QR code
            qr_data = json.dumps(team_data)
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)

            # Create QR code image
            qr_image = qr.make_image(fill_color="black", back_color="white")

            # Convert to base64
            img_buffer = io.BytesIO()
            qr_image.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            qr_base64 = base64.b64encode(img_buffer.getvalue()).decode()

            return QRCodeResponse(
                message=f"QR code generated successfully for team {request.team_number}",
                qr_code_base64=qr_base64,
                encoded_data=team_data
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating team card: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-hole-card", response_model=QRCodeResponse)
async def generate_hole_card(request: GenerateHoleCardRequest):
    """
    Takes a course name and hole number and generates a QR code with the course and hole information encoded into it.
    """
    try:
        with get_db_session() as session:
            # Get hole and course information
            hole_query = """
            MATCH (c:Course {name: $course_name})-[:HAS_HOLE]->(h:Hole {number: $hole_number})
            OPTIONAL MATCH (l:Location)-[:HAS_COURSE]->(c)
            OPTIONAL MATCH (t:Tournament)-[:USES]->(c)
            WITH c, h, l, collect(DISTINCT {
                tournament_name: t.name,
                tournament_active: t.active
            }) as tournaments
            RETURN c.name as course_name,
                   c.par as course_par,
                   h.name as hole_name,
                   h.number as hole_number,
                   h.par as hole_par,
                   l.name as location_name,
                   tournaments
            """

            result = session.run(hole_query, 
                               course_name=request.course_name,
                               hole_number=request.hole_number)
            record = result.single()

            if not record:
                raise HTTPException(
                    status_code=404,
                    detail=f"Hole {request.hole_number} not found on course {request.course_name}"
                )

            # Prepare hole data for QR code
            hole_data = {
                "type": "hole_card",
                "course_name": record["course_name"],
                "course_par": record["course_par"],
                "hole_name": record["hole_name"],
                "hole_number": record["hole_number"],
                "hole_par": record["hole_par"],
                "location_name": record["location_name"],
                "tournaments": [t for t in record["tournaments"] if t["tournament_name"] is not None],
                "generated_at": "2025-08-23T00:00:00Z"
            }

            # Generate QR code
            qr_data = json.dumps(hole_data)
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)

            # Create QR code image
            qr_image = qr.make_image(fill_color="black", back_color="white")

            # Convert to base64
            img_buffer = io.BytesIO()
            qr_image.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            qr_base64 = base64.b64encode(img_buffer.getvalue()).decode()

            return QRCodeResponse(
                message=f"QR code generated successfully for hole {request.hole_number} on {request.course_name}",
                qr_code_base64=qr_base64,
                encoded_data=hole_data
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating hole card: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Health check endpoint
@app.get("/health")
async def health_check():
    try:
        with get_db_session() as session:
            result = session.run("RETURN 1 as test")
            record = result.single()
            if record and record['test'] == 1:
                return {"status": "healthy", "database": "connected"}
            else:
                return {"status": "unhealthy", "database": "connection_failed"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "database": "connection_failed", "error": str(e)}

# Cleanup on shutdown
@app.on_event("shutdown")
async def shutdown():
    driver.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
