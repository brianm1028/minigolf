from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from neo4j import GraphDatabase
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import logging
from contextlib import contextmanager
from pathlib import Path
from logging.handlers import RotatingFileHandler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

log_file = "/home/minigolf/log/app.log"
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# File handler for logging to a file with rotation
file_handler = RotatingFileHandler(log_file, maxBytes=1024*1024*5, backupCount=5) # 5MB per file, 5 backup files
file_handler.setFormatter(log_formatter)

# Stream handler for console output (optional)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)

# Get the root logger and add handlers
logger.setLevel(logging.INFO) # Set desired logging level
logger.addHandler(file_handler)
logger.addHandler(stream_handler) 

# FastAPI app
app = FastAPI(title="Minigolf Tournament API", version="1.0.0")

# Import and mount tournament application
try:
    from tournament_app import app as tournament_app
    app.mount("/tournament", tournament_app, name="tournament")
    app.mount("/mobile", StaticFiles(directory=Path("mobile2"), html=True))
    app.mount("/leaderboard", StaticFiles(directory=Path("leaderboard"), html=True))
    logger.info("Tournament application mounted successfully at /tournament")
except ImportError as e:
    logger.warning(f"Could not import tournament_app: {e}")
except Exception as e:
    logger.error(f"Error mounting tournament application: {e}")

# Neo4j connection settings
NEO4J_URI = "bolt://raidersofthelostpar.org:7687"
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

# Pydantic Models for Nodes
class LocationCreate(BaseModel):
    name: str

class LocationUpdate(BaseModel):
    name: Optional[str] = None

class LocationResponse(BaseModel):
    id: str
    name: str

class CourseCreate(BaseModel):
    name: str
    par: int

class CourseUpdate(BaseModel):
    name: Optional[str] = None
    par: Optional[int] = None

class CourseResponse(BaseModel):
    id: str
    name: str
    par: int

class HoleCreate(BaseModel):
    name: str
    number: int
    par: int

class HoleUpdate(BaseModel):
    name: Optional[str] = None
    number: Optional[int] = None
    par: Optional[int] = None

class HoleResponse(BaseModel):
    id: str
    name: str
    number: int
    par: int

class TournamentCreate(BaseModel):
    name: str
    active: bool = True

class TournamentUpdate(BaseModel):
    name: Optional[str] = None
    active: Optional[bool] = None

class TournamentResponse(BaseModel):
    id: str
    name: str
    active: bool

class TeamCreate(BaseModel):
    name: str
    number: int

class TeamUpdate(BaseModel):
    name: Optional[str] = None
    number: Optional[int] = None

class TeamResponse(BaseModel):
    id: str
    name: str
    number: int

class DepartmentCreate(BaseModel):
    name: str

class DepartmentUpdate(BaseModel):
    name: Optional[str] = None

class DepartmentResponse(BaseModel):
    id: str
    name: str

class PlayerCreate(BaseModel):
    name: str
    number: int
    email: str

class PlayerUpdate(BaseModel):
    name: Optional[str] = None
    number: Optional[int] = None
    email: Optional[str] = None

class PlayerResponse(BaseModel):
    id: str
    name: str
    number: int
    email: str

class TeamRoundCreate(BaseModel):
    total: int
    average: float
    rank: int
    active: bool = True

class TeamRoundUpdate(BaseModel):
    total: Optional[int] = None
    average: Optional[float] = None
    rank: Optional[int] = None
    active: Optional[bool] = None

class TeamRoundResponse(BaseModel):
    id: str
    total: int
    average: float
    rank: int
    active: bool

class PlayerRoundCreate(BaseModel):
    total: int
    average: float
    rank: int
    active: bool = True

class PlayerRoundUpdate(BaseModel):
    total: Optional[int] = None
    average: Optional[float] = None
    rank: Optional[int] = None
    active: Optional[bool] = None

class PlayerRoundResponse(BaseModel):
    id: str
    total: int
    average: float
    rank: int
    active: bool

# Pydantic Models for Relationships
class RelationshipCreate(BaseModel):
    from_id: str
    to_id: str

class RelationshipResponse(BaseModel):
    id: str
    from_id: str
    to_id: str

# Utility functions
def node_to_dict(node):
    """Convert Neo4j node to dictionary"""
    result = dict(node)
    result['id'] = node.element_id
    return result

def relationship_to_dict(relationship):
    """Convert Neo4j relationship to dictionary"""
    return {
        'id': relationship.element_id,
        'from_id': relationship.start_node.element_id,
        'to_id': relationship.end_node.element_id
    }

# Generic CRUD operations
def create_node(session, label: str, properties: dict):
    """Generic function to create a node"""
    query = f"CREATE (n:{label} $props) RETURN n"
    result = session.run(query, props=properties)
    record = result.single()
    if record:
        return node_to_dict(record['n'])
    return None

def get_node(session, label: str, node_id: str):
    """Generic function to get a node by ID"""
    query = f"MATCH (n:{label}) WHERE n.number = $id RETURN n"
    print(query)
    print(node_id)
    result = session.run(query, id=node_id)
    record = result.single()
    print(record)
    if record:
        return node_to_dict(record['n'])
    return None

def get_all_nodes(session, label: str):
    """Generic function to get all nodes of a label"""
    query = f"MATCH (n:{label}) RETURN n"
    result = session.run(query)
    return [node_to_dict(record['n']) for record in result]

def update_node(session, label: str, node_id: str, properties: dict):
    """Generic function to update a node"""
    # Filter out None values
    properties = {k: v for k, v in properties.items() if v is not None}
    if not properties:
        return get_node(session, label, node_id)

    set_clauses = [f"n.{key} = ${key}" for key in properties.keys()]
    print(properties)
    query = f"MATCH (n:{label}) WHERE n.number = $id SET {', '.join(set_clauses)} RETURN n"
    print(query)
    print(node_id)
    result = session.run(query, id=int(node_id), **properties)
    record = result.single()
    print(record)
    if record:
        return node_to_dict(record['n'])
    return None

def delete_node(session, label: str, node_id: str):
    """Generic function to delete a node"""
    query = f"MATCH (n:{label}) WHERE elementId(n) = $id DETACH DELETE n"
    result = session.run(query, id=node_id)
    return result.consume().counters.nodes_deleted > 0

def create_relationship(session, from_label: str, to_label: str, relationship_type: str, from_id: str, to_id: str):
    """Generic function to create a relationship"""
    query = f"""
    MATCH (from:{from_label}) WHERE from.name = $from_id
    MATCH (to:{to_label}) WHERE to.name = $to_id
    CREATE (from)-[r:{relationship_type}]->(to)
    RETURN r, from, to
    """
    result = session.run(query, from_id=from_id, to_id=to_id)
    record = result.single()
    if record:
        return relationship_to_dict(record['r'])
    return None

def get_relationship(session, relationship_type: str, rel_id: str):
    """Generic function to get a relationship by ID"""
    query = f"MATCH ()-[r:{relationship_type}]-() WHERE elementId(r) = $id RETURN r, startNode(r) as from, endNode(r) as to"
    result = session.run(query, id=rel_id)
    record = result.single()
    if record:
        return relationship_to_dict(record['r'])
    return None

def get_all_relationships(session, relationship_type: str):
    """Generic function to get all relationships of a type"""
    query = f"MATCH ()-[r:{relationship_type}]-() RETURN r, startNode(r) as from, endNode(r) as to"
    result = session.run(query)
    return [relationship_to_dict(record['r']) for record in result]

def delete_relationship(session, relationship_type: str, rel_id: str):
    """Generic function to delete a relationship"""
    query = f"MATCH ()-[r:{relationship_type}]-() WHERE elementId(r) = $id DELETE r"
    result = session.run(query, id=rel_id)
    return result.consume().counters.relationships_deleted > 0

# Location endpoints
@app.post("/locations", response_model=LocationResponse)
async def create_location(location: LocationCreate):
    try:
        with get_db_session() as session:
            result = create_node(session, "Location", location.dict())
            if result:
                return LocationResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create location")
    except Exception as e:
        logger.error(f"Error creating location: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/locations", response_model=List[LocationResponse])
async def get_locations():
    try:
        with get_db_session() as session:
            results = get_all_nodes(session, "Location")
            return [LocationResponse(**result) for result in results]
    except Exception as e:
        logger.error(f"Error getting locations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/locations/{location_id}", response_model=LocationResponse)
async def get_location(location_id: str):
    try:
        with get_db_session() as session:
            result = get_node(session, "Location", location_id)
            if result:
                return LocationResponse(**result)
            raise HTTPException(status_code=404, detail="Location not found")
    except Exception as e:
        logger.error(f"Error getting location: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/locations/{location_id}", response_model=LocationResponse)
async def update_location(location_id: str, location: LocationUpdate):
    try:
        with get_db_session() as session:
            result = update_node(session, "Location", location_id, location.dict())
            if result:
                return LocationResponse(**result)
            raise HTTPException(status_code=404, detail="Location not found")
    except Exception as e:
        logger.error(f"Error updating location: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/locations/{location_id}")
async def delete_location(location_id: str):
    try:
        with get_db_session() as session:
            success = delete_node(session, "Location", location_id)
            if success:
                return {"message": "Location deleted successfully"}
            raise HTTPException(status_code=404, detail="Location not found")
    except Exception as e:
        logger.error(f"Error deleting location: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Course endpoints
@app.post("/courses", response_model=CourseResponse)
async def create_course(course: CourseCreate):
    try:
        with get_db_session() as session:
            result = create_node(session, "Course", course.dict())
            if result:
                return CourseResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create course")
    except Exception as e:
        logger.error(f"Error creating course: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/courses", response_model=List[CourseResponse])
async def get_courses():
    try:
        with get_db_session() as session:
            results = get_all_nodes(session, "Course")
            return [CourseResponse(**result) for result in results]
    except Exception as e:
        logger.error(f"Error getting courses: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/courses/{course_id}", response_model=CourseResponse)
async def get_course(course_id: str):
    try:
        with get_db_session() as session:
            result = get_node(session, "Course", course_id)
            if result:
                return CourseResponse(**result)
            raise HTTPException(status_code=404, detail="Course not found")
    except Exception as e:
        logger.error(f"Error getting course: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/courses/{course_id}", response_model=CourseResponse)
async def update_course(course_id: str, course: CourseUpdate):
    try:
        with get_db_session() as session:
            result = update_node(session, "Course", course_id, course.dict())
            if result:
                return CourseResponse(**result)
            raise HTTPException(status_code=404, detail="Course not found")
    except Exception as e:
        logger.error(f"Error updating course: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/courses/{course_id}")
async def delete_course(course_id: str):
    try:
        with get_db_session() as session:
            success = delete_node(session, "Course", course_id)
            if success:
                return {"message": "Course deleted successfully"}
            raise HTTPException(status_code=404, detail="Course not found")
    except Exception as e:
        logger.error(f"Error deleting course: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/courses/{course_name}/holes", response_model=List[HoleResponse])
async def get_holes_for_course(course_name: str):
    """Get all holes for a specific course by course name"""
    try:
        with get_db_session() as session:
            query = """
            MATCH (c:Course {name: $course_name})-[:HAS_HOLE]->(h:Hole)
            RETURN h
            ORDER BY h.number
            """
            result = session.run(query, course_name=course_name)

            holes = []
            for record in result:
                hole_dict = node_to_dict(record['h'])
                holes.append(HoleResponse(**hole_dict))

            if not holes:
                # Check if course exists
                course_check = session.run("MATCH (c:Course {name: $course_name}) RETURN c", course_name=course_name)
                if not course_check.single():
                    raise HTTPException(status_code=404, detail=f"Course '{course_name}' not found")
                # Course exists but has no holes
                return []

            return holes
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting holes for course '{course_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Hole endpoints
@app.post("/holes", response_model=HoleResponse)
async def create_hole(hole: HoleCreate):
    try:
        with get_db_session() as session:
            result = create_node(session, "Hole", hole.dict())
            if result:
                return HoleResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create hole")
    except Exception as e:
        logger.error(f"Error creating hole: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/holes", response_model=List[HoleResponse])
async def get_holes():
    try:
        with get_db_session() as session:
            results = get_all_nodes(session, "Hole")
            return [HoleResponse(**result) for result in results]
    except Exception as e:
        logger.error(f"Error getting holes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/holes/{hole_id}", response_model=HoleResponse)
async def get_hole(hole_id: str):
    try:
        with get_db_session() as session:
            result = get_node(session, "Hole", hole_id)
            if result:
                return HoleResponse(**result)
            raise HTTPException(status_code=404, detail="Hole not found")
    except Exception as e:
        logger.error(f"Error getting hole: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/holes/{hole_id}", response_model=HoleResponse)
async def update_hole(hole_id: str, hole: HoleUpdate):
    try:
        with get_db_session() as session:
            result = update_node(session, "Hole", hole_id, hole.dict())
            if result:
                return HoleResponse(**result)
            raise HTTPException(status_code=404, detail="Hole not found")
    except Exception as e:
        logger.error(f"Error updating hole: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/holes/{hole_id}")
async def delete_hole(hole_id: str):
    try:
        with get_db_session() as session:
            success = delete_node(session, "Hole", hole_id)
            if success:
                return {"message": "Hole deleted successfully"}
            raise HTTPException(status_code=404, detail="Hole not found")
    except Exception as e:
        logger.error(f"Error deleting hole: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Tournament endpoints
@app.post("/tournaments", response_model=TournamentResponse)
async def create_tournament(tournament: TournamentCreate):
    try:
        with get_db_session() as session:
            result = create_node(session, "Tournament", tournament.dict())
            if result:
                return TournamentResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create tournament")
    except Exception as e:
        logger.error(f"Error creating tournament: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tournaments", response_model=List[TournamentResponse])
async def get_tournaments():
    try:
        with get_db_session() as session:
            results = get_all_nodes(session, "Tournament")
            return [TournamentResponse(**result) for result in results]
    except Exception as e:
        logger.error(f"Error getting tournaments: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tournaments/{tournament_id}", response_model=TournamentResponse)
async def get_tournament(tournament_id: str):
    try:
        with get_db_session() as session:
            result = get_node(session, "Tournament", tournament_id)
            if result:
                return TournamentResponse(**result)
            raise HTTPException(status_code=404, detail="Tournament not found")
    except Exception as e:
        logger.error(f"Error getting tournament: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/tournaments/{tournament_id}", response_model=TournamentResponse)
async def update_tournament(tournament_id: str, tournament: TournamentUpdate):
    try:
        with get_db_session() as session:
            result = update_node(session, "Tournament", tournament_id, tournament.dict())
            if result:
                return TournamentResponse(**result)
            raise HTTPException(status_code=404, detail="Tournament not found")
    except Exception as e:
        logger.error(f"Error updating tournament: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/tournaments/{tournament_id}")
async def delete_tournament(tournament_id: str):
    try:
        with get_db_session() as session:
            success = delete_node(session, "Tournament", tournament_id)
            if success:
                return {"message": "Tournament deleted successfully"}
            raise HTTPException(status_code=404, detail="Tournament not found")
    except Exception as e:
        logger.error(f"Error deleting tournament: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Team endpoints
@app.post("/teams", response_model=TeamResponse)
async def create_team(team: TeamCreate):
    try:
        with get_db_session() as session:
            result = create_node(session, "Team", team.dict())
            if result:
                return TeamResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create team")
    except Exception as e:
        logger.error(f"Error creating team: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/teams", response_model=List[TeamResponse])
async def get_teams():
    try:
        with get_db_session() as session:
            results = get_all_nodes(session, "Team")
            return [TeamResponse(**result) for result in results]
    except Exception as e:
        logger.error(f"Error getting teams: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/teams/{team_id}", response_model=TeamResponse)
async def get_team(team_id: str):
    try:
        with get_db_session() as session:
            result = get_node(session, "Team", team_id)
            if result:
                return TeamResponse(**result)
            raise HTTPException(status_code=404, detail="Team not found")
    except Exception as e:
        logger.error(f"Error getting team: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/teams/{team_id}", response_model=TeamResponse)
async def update_team(team_id: str, team: TeamUpdate):
    try:
        with get_db_session() as session:
            result = update_node(session, "Team", team_id, team.dict())
            if result:
                return TeamResponse(**result)
            raise HTTPException(status_code=404, detail="Team not found")
    except Exception as e:
        logger.error(f"Error updating team: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/teams/{team_id}")
async def delete_team(team_id: str):
    try:
        with get_db_session() as session:
            success = delete_node(session, "Team", team_id)
            if success:
                return {"message": "Team deleted successfully"}
            raise HTTPException(status_code=404, detail="Team not found")
    except Exception as e:
        logger.error(f"Error deleting team: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/teams/{team_number}/players", response_model=List[PlayerResponse])
async def get_players_for_team(team_number: int):
    """Get all holes for a specific course by course name"""
    try:
        with get_db_session() as session:
            query = """
            MATCH (p:Player)-[:MEMBER_OF]->(t:Team {number: $team_number})
            RETURN p
            ORDER BY p.name
            """
            result = session.run(query, team_number=team_number)

            players = []
            for record in result:
                player_dict = node_to_dict(record['p'])
                players.append(PlayerResponse(**player_dict))

            if not players:
                # Check if team exists
                team_check = session.run("MATCH (t:Team {number: $team_number}) RETURN t", team_number=str(team_number))
                if not team_check.single():
                    raise HTTPException(status_code=404, detail=f"Team '{str(team_number)}' not found")
                # Team exists but has no players
                return []

            return players
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting players for team '{str(team_number)}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Department endpoints
@app.post("/departments", response_model=DepartmentResponse)
async def create_department(department: DepartmentCreate):
    try:
        with get_db_session() as session:
            result = create_node(session, "Department", department.dict())
            if result:
                return DepartmentResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create department")
    except Exception as e:
        logger.error(f"Error creating department: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/departments", response_model=List[DepartmentResponse])
async def get_departments():
    try:
        with get_db_session() as session:
            results = get_all_nodes(session, "Department")
            return [DepartmentResponse(**result) for result in results]
    except Exception as e:
        logger.error(f"Error getting departments: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/departments/{department_id}", response_model=DepartmentResponse)
async def get_department(department_id: str):
    try:
        with get_db_session() as session:
            result = get_node(session, "Department", department_id)
            if result:
                return DepartmentResponse(**result)
            raise HTTPException(status_code=404, detail="Department not found")
    except Exception as e:
        logger.error(f"Error getting department: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/departments/{department_id}", response_model=DepartmentResponse)
async def update_department(department_id: str, department: DepartmentUpdate):
    try:
        with get_db_session() as session:
            result = update_node(session, "Department", department_id, department.dict())
            if result:
                return DepartmentResponse(**result)
            raise HTTPException(status_code=404, detail="Department not found")
    except Exception as e:
        logger.error(f"Error updating department: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/departments/{department_id}")
async def delete_department(department_id: str):
    try:
        with get_db_session() as session:
            success = delete_node(session, "Department", department_id)
            if success:
                return {"message": "Department deleted successfully"}
            raise HTTPException(status_code=404, detail="Department not found")
    except Exception as e:
        logger.error(f"Error deleting department: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Player endpoints
@app.post("/players", response_model=PlayerResponse)
async def create_player(player: PlayerCreate):
    try:
        with get_db_session() as session:
            result = create_node(session, "Player", player.dict())
            if result:
                return PlayerResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create player")
    except Exception as e:
        logger.error(f"Error creating player: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/players", response_model=List[PlayerResponse])
async def get_players():
    try:
        with get_db_session() as session:
            results = get_all_nodes(session, "Player")
            return [PlayerResponse(**result) for result in results]
    except Exception as e:
        logger.error(f"Error getting players: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/players/{player_id}", response_model=PlayerResponse)
async def get_player(player_id: str):
    try:
        with get_db_session() as session:
            result = get_node(session, "Player", player_id)
            if result:
                return PlayerResponse(**result)
            raise HTTPException(status_code=404, detail="Player not found")
    except Exception as e:
        logger.error(f"Error getting player: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/players/{player_id}", response_model=PlayerResponse)
async def update_player(player_id: str, player: PlayerUpdate):
    try:
        with get_db_session() as session:
            result = update_node(session, "Player", player_id, {'name':player.name})
            if result:
                return PlayerResponse(**result)
            raise HTTPException(status_code=404, detail="Player not found")
    except Exception as e:
        logger.error(f"Error updating player: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/players/{player_id}")
async def delete_player(player_id: str):
    try:
        with get_db_session() as session:
            success = delete_node(session, "Player", player_id)
            if success:
                return {"message": "Player deleted successfully"}
            raise HTTPException(status_code=404, detail="Player not found")
    except Exception as e:
        logger.error(f"Error deleting player: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# TeamRound endpoints
@app.post("/team-rounds", response_model=TeamRoundResponse)
async def create_team_round(team_round: TeamRoundCreate):
    try:
        with get_db_session() as session:
            result = create_node(session, "TeamRound", team_round.dict())
            if result:
                return TeamRoundResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create team round")
    except Exception as e:
        logger.error(f"Error creating team round: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/team-rounds", response_model=List[TeamRoundResponse])
async def get_team_rounds():
    try:
        with get_db_session() as session:
            results = get_all_nodes(session, "TeamRound")
            return [TeamRoundResponse(**result) for result in results]
    except Exception as e:
        logger.error(f"Error getting team rounds: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/team-rounds/{team_round_id}", response_model=TeamRoundResponse)
async def get_team_round(team_round_id: str):
    try:
        with get_db_session() as session:
            result = get_node(session, "TeamRound", team_round_id)
            if result:
                return TeamRoundResponse(**result)
            raise HTTPException(status_code=404, detail="Team round not found")
    except Exception as e:
        logger.error(f"Error getting team round: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/team-rounds/{team_round_id}", response_model=TeamRoundResponse)
async def update_team_round(team_round_id: str, team_round: TeamRoundUpdate):
    try:
        with get_db_session() as session:
            result = update_node(session, "TeamRound", team_round_id, team_round.dict())
            if result:
                return TeamRoundResponse(**result)
            raise HTTPException(status_code=404, detail="Team round not found")
    except Exception as e:
        logger.error(f"Error updating team round: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/team-rounds/{team_round_id}")
async def delete_team_round(team_round_id: str):
    try:
        with get_db_session() as session:
            success = delete_node(session, "TeamRound", team_round_id)
            if success:
                return {"message": "Team round deleted successfully"}
            raise HTTPException(status_code=404, detail="Team round not found")
    except Exception as e:
        logger.error(f"Error deleting team round: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# PlayerRound endpoints
@app.post("/player-rounds", response_model=PlayerRoundResponse)
async def create_player_round(player_round: PlayerRoundCreate):
    try:
        with get_db_session() as session:
            result = create_node(session, "PlayerRound", player_round.dict())
            if result:
                return PlayerRoundResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create player round")
    except Exception as e:
        logger.error(f"Error creating player round: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/player-rounds", response_model=List[PlayerRoundResponse])
async def get_player_rounds():
    try:
        with get_db_session() as session:
            results = get_all_nodes(session, "PlayerRound")
            return [PlayerRoundResponse(**result) for result in results]
    except Exception as e:
        logger.error(f"Error getting player rounds: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/player-rounds/{player_round_id}", response_model=PlayerRoundResponse)
async def get_player_round(player_round_id: str):
    try:
        with get_db_session() as session:
            result = get_node(session, "PlayerRound", player_round_id)
            if result:
                return PlayerRoundResponse(**result)
            raise HTTPException(status_code=404, detail="Player round not found")
    except Exception as e:
        logger.error(f"Error getting player round: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/player-rounds/{player_round_id}", response_model=PlayerRoundResponse)
async def update_player_round(player_round_id: str, player_round: PlayerRoundUpdate):
    try:
        with get_db_session() as session:
            result = update_node(session, "PlayerRound", player_round_id, player_round.dict())
            if result:
                return PlayerRoundResponse(**result)
            raise HTTPException(status_code=404, detail="Player round not found")
    except Exception as e:
        logger.error(f"Error updating player round: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/player-rounds/{player_round_id}")
async def delete_player_round(player_round_id: str):
    try:
        with get_db_session() as session:
            success = delete_node(session, "PlayerRound", player_round_id)
            if success:
                return {"message": "Player round deleted successfully"}
            raise HTTPException(status_code=404, detail="Player round not found")
    except Exception as e:
        logger.error(f"Error deleting player round: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Relationship endpoints

# Location-[:HAS_COURSE]->Course
@app.post("/relationships/location-has-course", response_model=RelationshipResponse)
async def create_location_has_course(relationship: RelationshipCreate):
    try:
        with get_db_session() as session:
            result = create_relationship(session, "Location", "Course", "HAS_COURSE", 
                                       relationship.from_id, relationship.to_id)
            if result:
                return RelationshipResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create relationship")
    except Exception as e:
        logger.error(f"Error creating location-has-course relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/relationships/location-has-course", response_model=List[RelationshipResponse])
async def get_location_has_course_relationships():
    try:
        with get_db_session() as session:
            results = get_all_relationships(session, "HAS_COURSE")
            return [RelationshipResponse(**result) for result in results]
    except Exception as e:
        logger.error(f"Error getting location-has-course relationships: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/relationships/location-has-course/{relationship_id}")
async def delete_location_has_course(relationship_id: str):
    try:
        with get_db_session() as session:
            success = delete_relationship(session, "HAS_COURSE", relationship_id)
            if success:
                return {"message": "Relationship deleted successfully"}
            raise HTTPException(status_code=404, detail="Relationship not found")
    except Exception as e:
        logger.error(f"Error deleting location-has-course relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Course-[:HAS_HOLE]->Hole
@app.post("/relationships/course-has-hole", response_model=RelationshipResponse)
async def create_course_has_hole(relationship: RelationshipCreate):
    try:
        with get_db_session() as session:
            result = create_relationship(session, "Course", "Hole", "HAS_HOLE", 
                                       relationship.from_id, relationship.to_id)
            if result:
                return RelationshipResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create relationship")
    except Exception as e:
        logger.error(f"Error creating course-has-hole relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/relationships/course-has-hole", response_model=List[RelationshipResponse])
async def get_course_has_hole_relationships():
    try:
        with get_db_session() as session:
            results = get_all_relationships(session, "HAS_HOLE")
            return [RelationshipResponse(**result) for result in results]
    except Exception as e:
        logger.error(f"Error getting course-has-hole relationships: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/relationships/course-has-hole/{relationship_id}")
async def delete_course_has_hole(relationship_id: str):
    try:
        with get_db_session() as session:
            success = delete_relationship(session, "HAS_HOLE", relationship_id)
            if success:
                return {"message": "Relationship deleted successfully"}
            raise HTTPException(status_code=404, detail="Relationship not found")
    except Exception as e:
        logger.error(f"Error deleting course-has-hole relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Tournament-[:HAS_TEAM]->Team
@app.post("/relationships/tournament-has-team", response_model=RelationshipResponse)
async def create_tournament_has_team(relationship: RelationshipCreate):
    try:
        with get_db_session() as session:
            result = create_relationship(session, "Tournament", "Team", "HAS_TEAM", 
                                       relationship.from_id, relationship.to_id)
            if result:
                return RelationshipResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create relationship")
    except Exception as e:
        logger.error(f"Error creating tournament-has-team relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/relationships/tournament-has-team", response_model=List[RelationshipResponse])
async def get_tournament_has_team_relationships():
    try:
        with get_db_session() as session:
            results = get_all_relationships(session, "HAS_TEAM")
            return [RelationshipResponse(**result) for result in results]
    except Exception as e:
        logger.error(f"Error getting tournament-has-team relationships: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/relationships/tournament-has-team/{relationship_id}")
async def delete_tournament_has_team(relationship_id: str):
    try:
        with get_db_session() as session:
            success = delete_relationship(session, "HAS_TEAM", relationship_id)
            if success:
                return {"message": "Relationship deleted successfully"}
            raise HTTPException(status_code=404, detail="Relationship not found")
    except Exception as e:
        logger.error(f"Error deleting tournament-has-team relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# TeamRound-[:IN_TOURNAMENT]->Tournament
@app.post("/relationships/teamround-in-tournament", response_model=RelationshipResponse)
async def create_teamround_in_tournament(relationship: RelationshipCreate):
    try:
        with get_db_session() as session:
            result = create_relationship(session, "TeamRound", "Tournament", "IN_TOURNAMENT", 
                                       relationship.from_id, relationship.to_id)
            if result:
                return RelationshipResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create relationship")
    except Exception as e:
        logger.error(f"Error creating teamround-in-tournament relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/relationships/teamround-in-tournament", response_model=List[RelationshipResponse])
async def get_teamround_in_tournament_relationships():
    try:
        with get_db_session() as session:
            results = get_all_relationships(session, "IN_TOURNAMENT")
            return [RelationshipResponse(**result) for result in results]
    except Exception as e:
        logger.error(f"Error getting teamround-in-tournament relationships: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/relationships/teamround-in-tournament/{relationship_id}")
async def delete_teamround_in_tournament(relationship_id: str):
    try:
        with get_db_session() as session:
            success = delete_relationship(session, "IN_TOURNAMENT", relationship_id)
            if success:
                return {"message": "Relationship deleted successfully"}
            raise HTTPException(status_code=404, detail="Relationship not found")
    except Exception as e:
        logger.error(f"Error deleting teamround-in-tournament relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Player-[:MEMBER_OF]->Team
@app.post("/relationships/player-member-of-team", response_model=RelationshipResponse)
async def create_player_member_of_team(relationship: RelationshipCreate):
    try:
        with get_db_session() as session:
            result = create_relationship(session, "Player", "Team", "MEMBER_OF", 
                                       relationship.from_id, relationship.to_id)
            if result:
                return RelationshipResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create relationship")
    except Exception as e:
        logger.error(f"Error creating player-member-of-team relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/relationships/player-member-of-team", response_model=List[RelationshipResponse])
async def get_player_member_of_team_relationships():
    try:
        with get_db_session() as session:
            # Use a more specific query since MEMBER_OF appears in multiple relationships
            query = "MATCH (p:Player)-[r:MEMBER_OF]->(t:Team) RETURN r, p as from, t as to"
            result = session.run(query)
            return [relationship_to_dict(record['r']) for record in result]
    except Exception as e:
        logger.error(f"Error getting player-member-of-team relationships: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/relationships/player-member-of-team/{relationship_id}")
async def delete_player_member_of_team(relationship_id: str):
    try:
        with get_db_session() as session:
            query = "MATCH (p:Player)-[r:MEMBER_OF]->(t:Team) WHERE elementId(r) = $id DELETE r"
            result = session.run(query, id=relationship_id)
            success = result.consume().counters.relationships_deleted > 0
            if success:
                return {"message": "Relationship deleted successfully"}
            raise HTTPException(status_code=404, detail="Relationship not found")
    except Exception as e:
        logger.error(f"Error deleting player-member-of-team relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Player-[:MEMBER_OF]->Department
@app.post("/relationships/player-member-of-department", response_model=RelationshipResponse)
async def create_player_member_of_department(relationship: RelationshipCreate):
    try:
        with get_db_session() as session:
            result = create_relationship(session, "Player", "Department", "MEMBER_OF", 
                                       relationship.from_id, relationship.to_id)
            if result:
                return RelationshipResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create relationship")
    except Exception as e:
        logger.error(f"Error creating player-member-of-department relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/relationships/player-member-of-department", response_model=List[RelationshipResponse])
async def get_player_member_of_department_relationships():
    try:
        with get_db_session() as session:
            # Use a more specific query since MEMBER_OF appears in multiple relationships
            query = "MATCH (p:Player)-[r:MEMBER_OF]->(d:Department) RETURN r, p as from, d as to"
            result = session.run(query)
            return [relationship_to_dict(record['r']) for record in result]
    except Exception as e:
        logger.error(f"Error getting player-member-of-department relationships: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/relationships/player-member-of-department/{relationship_id}")
async def delete_player_member_of_department(relationship_id: str):
    try:
        with get_db_session() as session:
            query = "MATCH (p:Player)-[r:MEMBER_OF]->(d:Department) WHERE elementId(r) = $id DELETE r"
            result = session.run(query, id=relationship_id)
            success = result.consume().counters.relationships_deleted > 0
            if success:
                return {"message": "Relationship deleted successfully"}
            raise HTTPException(status_code=404, detail="Relationship not found")
    except Exception as e:
        logger.error(f"Error deleting player-member-of-department relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Tournament-[:PLAYED_AT]->Location
@app.post("/relationships/tournament-played-at-location", response_model=RelationshipResponse)
async def create_tournament_played_at_location(relationship: RelationshipCreate):
    try:
        with get_db_session() as session:
            result = create_relationship(session, "Tournament", "Location", "PLAYED_AT", 
                                       relationship.from_id, relationship.to_id)
            if result:
                return RelationshipResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create relationship")
    except Exception as e:
        logger.error(f"Error creating tournament-played-at-location relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/relationships/tournament-played-at-location", response_model=List[RelationshipResponse])
async def get_tournament_played_at_location_relationships():
    try:
        with get_db_session() as session:
            results = get_all_relationships(session, "PLAYED_AT")
            return [RelationshipResponse(**result) for result in results]
    except Exception as e:
        logger.error(f"Error getting tournament-played-at-location relationships: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/relationships/tournament-played-at-location/{relationship_id}")
async def delete_tournament_played_at_location(relationship_id: str):
    try:
        with get_db_session() as session:
            success = delete_relationship(session, "PLAYED_AT", relationship_id)
            if success:
                return {"message": "Relationship deleted successfully"}
            raise HTTPException(status_code=404, detail="Relationship not found")
    except Exception as e:
        logger.error(f"Error deleting tournament-played-at-location relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# PlayerRound-[:PLAYED_HOLE]->Hole
@app.post("/relationships/playerround-played-hole", response_model=RelationshipResponse)
async def create_playerround_played_hole(relationship: RelationshipCreate):
    try:
        with get_db_session() as session:
            result = create_relationship(session, "PlayerRound", "Hole", "PLAYED_HOLE", 
                                       relationship.from_id, relationship.to_id)
            if result:
                return RelationshipResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create relationship")
    except Exception as e:
        logger.error(f"Error creating playerround-played-hole relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/relationships/playerround-played-hole", response_model=List[RelationshipResponse])
async def get_playerround_played_hole_relationships():
    try:
        with get_db_session() as session:
            results = get_all_relationships(session, "PLAYED_HOLE")
            return [RelationshipResponse(**result) for result in results]
    except Exception as e:
        logger.error(f"Error getting playerround-played-hole relationships: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/relationships/playerround-played-hole/{relationship_id}")
async def delete_playerround_played_hole(relationship_id: str):
    try:
        with get_db_session() as session:
            success = delete_relationship(session, "PLAYED_HOLE", relationship_id)
            if success:
                return {"message": "Relationship deleted successfully"}
            raise HTTPException(status_code=404, detail="Relationship not found")
    except Exception as e:
        logger.error(f"Error deleting playerround-played-hole relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Team-[:PLAYED_ROUND]->TeamRound
@app.post("/relationships/team-played-round", response_model=RelationshipResponse)
async def create_team_played_round(relationship: RelationshipCreate):
    try:
        with get_db_session() as session:
            result = create_relationship(session, "Team", "TeamRound", "PLAYED_ROUND", 
                                       relationship.from_id, relationship.to_id)
            if result:
                return RelationshipResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create relationship")
    except Exception as e:
        logger.error(f"Error creating team-played-round relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/relationships/team-played-round", response_model=List[RelationshipResponse])
async def get_team_played_round_relationships():
    try:
        with get_db_session() as session:
            # Use a more specific query since PLAYED_ROUND appears in multiple relationships
            query = "MATCH (t:Team)-[r:PLAYED_ROUND]->(tr:TeamRound) RETURN r, t as from, tr as to"
            result = session.run(query)
            return [relationship_to_dict(record['r']) for record in result]
    except Exception as e:
        logger.error(f"Error getting team-played-round relationships: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/relationships/team-played-round/{relationship_id}")
async def delete_team_played_round(relationship_id: str):
    try:
        with get_db_session() as session:
            query = "MATCH (t:Team)-[r:PLAYED_ROUND]->(tr:TeamRound) WHERE elementId(r) = $id DELETE r"
            result = session.run(query, id=relationship_id)
            success = result.consume().counters.relationships_deleted > 0
            if success:
                return {"message": "Relationship deleted successfully"}
            raise HTTPException(status_code=404, detail="Relationship not found")
    except Exception as e:
        logger.error(f"Error deleting team-played-round relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Player-[:PLAYED_ROUND]->PlayerRound
@app.post("/relationships/player-played-round", response_model=RelationshipResponse)
async def create_player_played_round(relationship: RelationshipCreate):
    try:
        with get_db_session() as session:
            result = create_relationship(session, "Player", "PlayerRound", "PLAYED_ROUND", 
                                       relationship.from_id, relationship.to_id)
            if result:
                return RelationshipResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create relationship")
    except Exception as e:
        logger.error(f"Error creating player-played-round relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/relationships/player-played-round", response_model=List[RelationshipResponse])
async def get_player_played_round_relationships():
    try:
        with get_db_session() as session:
            # Use a more specific query since PLAYED_ROUND appears in multiple relationships
            query = "MATCH (p:Player)-[r:PLAYED_ROUND]->(pr:PlayerRound) RETURN r, p as from, pr as to"
            result = session.run(query)
            return [relationship_to_dict(record['r']) for record in result]
    except Exception as e:
        logger.error(f"Error getting player-played-round relationships: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/relationships/player-played-round/{relationship_id}")
async def delete_player_played_round(relationship_id: str):
    try:
        with get_db_session() as session:
            query = "MATCH (p:Player)-[r:PLAYED_ROUND]->(pr:PlayerRound) WHERE elementId(r) = $id DELETE r"
            result = session.run(query, id=relationship_id)
            success = result.consume().counters.relationships_deleted > 0
            if success:
                return {"message": "Relationship deleted successfully"}
            raise HTTPException(status_code=404, detail="Relationship not found")
    except Exception as e:
        logger.error(f"Error deleting player-played-round relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# PlayerRound-[:PLAYED_ROUND]->TeamRound
@app.post("/relationships/playerround-played-round-teamround", response_model=RelationshipResponse)
async def create_playerround_played_round_teamround(relationship: RelationshipCreate):
    try:
        with get_db_session() as session:
            result = create_relationship(session, "PlayerRound", "TeamRound", "PLAYED_ROUND", 
                                       relationship.from_id, relationship.to_id)
            if result:
                return RelationshipResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create relationship")
    except Exception as e:
        logger.error(f"Error creating playerround-played-round-teamround relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/relationships/playerround-played-round-teamround", response_model=List[RelationshipResponse])
async def get_playerround_played_round_teamround_relationships():
    try:
        with get_db_session() as session:
            # Use a more specific query since PLAYED_ROUND appears in multiple relationships
            query = "MATCH (pr:PlayerRound)-[r:PLAYED_ROUND]->(tr:TeamRound) RETURN r, pr as from, tr as to"
            result = session.run(query)
            return [relationship_to_dict(record['r']) for record in result]
    except Exception as e:
        logger.error(f"Error getting playerround-played-round-teamround relationships: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/relationships/playerround-played-round-teamround/{relationship_id}")
async def delete_playerround_played_round_teamround(relationship_id: str):
    try:
        with get_db_session() as session:
            query = "MATCH (pr:PlayerRound)-[r:PLAYED_ROUND]->(tr:TeamRound) WHERE elementId(r) = $id DELETE r"
            result = session.run(query, id=relationship_id)
            success = result.consume().counters.relationships_deleted > 0
            if success:
                return {"message": "Relationship deleted successfully"}
            raise HTTPException(status_code=404, detail="Relationship not found")
    except Exception as e:
        logger.error(f"Error deleting playerround-played-round-teamround relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Tournament-[:USES]->Course
@app.post("/relationships/tournament-uses-course", response_model=RelationshipResponse)
async def create_tournament_uses_course(relationship: RelationshipCreate):
    try:
        with get_db_session() as session:
            result = create_relationship(session, "Tournament", "Course", "USES", 
                                       relationship.from_id, relationship.to_id)
            if result:
                return RelationshipResponse(**result)
            raise HTTPException(status_code=500, detail="Failed to create relationship")
    except Exception as e:
        logger.error(f"Error creating tournament-uses-course relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/relationships/tournament-uses-course", response_model=List[RelationshipResponse])
async def get_tournament_uses_course_relationships():
    try:
        with get_db_session() as session:
            results = get_all_relationships(session, "USES")
            return [RelationshipResponse(**result) for result in results]
    except Exception as e:
        logger.error(f"Error getting tournament-uses-course relationships: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/relationships/tournament-uses-course/{relationship_id}")
async def delete_tournament_uses_course(relationship_id: str):
    try:
        with get_db_session() as session:
            success = delete_relationship(session, "USES", relationship_id)
            if success:
                return {"message": "Relationship deleted successfully"}
            raise HTTPException(status_code=404, detail="Relationship not found")
    except Exception as e:
        logger.error(f"Error deleting tournament-uses-course relationship: {e}")
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
    uvicorn.run(app, host="0.0.0.0", port=8000, ssl_keyfile="./minigolf.key", ssl_certfile="./minigolf.crt")
