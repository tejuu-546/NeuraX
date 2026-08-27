import os
from datetime import datetime
from typing import List, Optional

import networkx as nx
from dotenv import load_dotenv

from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END


# =====================================================
# ENVIRONMENT
# =====================================================

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not configured")


# =====================================================
# GEMINI AI
# =====================================================

llm = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash",
    google_api_key=GEMINI_API_KEY,
    temperature=0.2
)
# =====================================================
# INCIDENT MODEL
# =====================================================

class Incident(BaseModel):
    id: str = "INC-101"
    location: str
    hazard_type: str
    severity: int
    description: str
    blocked_nodes: List[str] = Field(default_factory=list)


# =====================================================
# AGENT ACTION
# =====================================================

class AgentAction(BaseModel):
    agent_name: str
    action_taken: str
    timestamp: str


# =====================================================
# EMERGENCY STATE
# =====================================================

class CampusEmergencyState(BaseModel):
    incident: Incident

    evacuation_route: List[str] = Field(
        default_factory=list
    )

    medical_dispatched: Optional[str] = None

    security_deployed: List[str] = Field(
        default_factory=list
    )

    facilities_actions: List[str] = Field(
        default_factory=list
    )

    public_alert: Optional[str] = None

    action_log: List[AgentAction] = Field(
        default_factory=list
    )
# =====================================================
# CAMPUS MAP
# =====================================================

CAMPUS_POS = {
    "Main_Gate": (0, 2),
    "Admin_Building": (2, 3),
    "Science_Block": (4, 3),
    "Health_Center": (6, 2),
    "Gate_2": (6, 0),
    "Hostel_A": (4, 0),
    "Hostel_B": (2, 0),
    "Sports_Complex": (6, 4)
}


def get_base_campus_graph():

    G = nx.Graph()

    G.add_nodes_from(CAMPUS_POS.keys())

    edges = [
        ("Main_Gate", "Admin_Building", 100),
        ("Admin_Building", "Science_Block", 150),
        ("Main_Gate", "Science_Block", 220),
        ("Science_Block", "Health_Center", 120),
        ("Gate_2", "Health_Center", 80),
        ("Gate_2", "Hostel_A", 110),
        ("Hostel_A", "Hostel_B", 90),
        ("Hostel_B", "Science_Block", 200),
        ("Health_Center", "Sports_Complex", 140)
    ]

    for u, v, weight in edges:
        G.add_edge(
            u,
            v,
            weight=weight
        )

    return G


campus_graph = get_base_campus_graph()
# =====================================================
# ROUTING AGENT
# =====================================================

def triage_and_routing_agent(
    state: CampusEmergencyState
):

    G = campus_graph.copy()

    # Remove blocked locations
    for blocked in state.incident.blocked_nodes:

        if G.has_node(blocked):
            G.remove_node(blocked)

    origin = state.incident.location

    safe_exits = [
        "Gate_2",
        "Main_Gate"
    ]

    best_path = []

    for exit_node in safe_exits:

        try:

            if (
                G.has_node(origin)
                and G.has_node(exit_node)
            ):

                path = nx.shortest_path(
                    G,
                    source=origin,
                    target=exit_node,
                    weight="weight"
                )

                if (
                    not best_path
                    or len(path) < len(best_path)
                ):
                    best_path = path

        except (
            nx.NetworkXNoPath,
            nx.NodeNotFound
        ):
            continue

    route_text = (
        " -> ".join(best_path)
        if best_path
        else "TRAPPED - SHELTER IN PLACE"
    )

    action = AgentAction(
        agent_name="Routing & Facilities Agent",
        action_taken=(
            f"Safe path determined: {route_text}. "
            f"HVAC/power isolated at {origin}."
        ),
        timestamp=datetime.now().strftime("%H:%M:%S")
    )

    return {
        "evacuation_route": best_path,

        "facilities_actions": [
            f"Isolated HVAC and power at {origin}"
        ],

        "action_log": (
            state.action_log + [action]
        )
    }

# =====================================================
# MEDICAL AGENT
# =====================================================

def medical_response_agent(
    state: CampusEmergencyState
):

    if state.incident.severity >= 4:
        unit = "ALS Ambulance-1 (Health Center)"
    else:
        unit = "Rapid First-Aid Squad"

    if state.evacuation_route:
        perimeter_target = state.evacuation_route[-1]
    else:
        perimeter_target = state.incident.location

    action = AgentAction(
        agent_name="Medical Response Agent",
        action_taken=(
            f"Dispatched {unit} "
            f"to perimeter pickup point "
            f"at {perimeter_target}."
        ),
        timestamp=datetime.now().strftime("%H:%M:%S")
    )

    return {
        "medical_dispatched": unit,

        "action_log": (
            state.action_log + [action]
        )
    }

# =====================================================
# SECURITY AGENT
# =====================================================

def security_agent(
    state: CampusEmergencyState
):

    action = AgentAction(
        agent_name="Security Operations Agent",
        action_taken=(
            f"Sealed building access at "
            f"{state.incident.location}. "
            f"Secured turnstiles and outer perimeter gates."
        ),
        timestamp=datetime.now().strftime("%H:%M:%S")
    )

    return {
        "security_deployed": [
            "Tactical Guard Alpha",
            "Perimeter Unit 2"
        ],

        "action_log": (
            state.action_log + [action]
        )
    }

# =====================================================
# COMMUNICATIONS AGENT
# =====================================================

def communications_agent(
    state: CampusEmergencyState
):

    if state.evacuation_route:

        route_description = (
            " -> ".join(
                state.evacuation_route
            )
        )

    else:

        route_description = (
            "Shelter in place immediately "
            "and await rescue."
        )

    prompt = f"""
You are the Campus Emergency Operations Center.

Generate a calm and authoritative emergency
broadcast message.

Keep it concise.

Incident:
{state.incident.hazard_type}

Location:
{state.incident.location}

Severity:
Level {state.incident.severity}/5

Description:
{state.incident.description}

Evacuation Route:
{route_description}
"""

    response = llm.invoke(prompt)

    alert = str(
        response.content
    ).strip()

    action = AgentAction(
        agent_name="Communications Agent",
        action_taken=(
            f"Emergency alert generated: {alert}"
        ),
        timestamp=datetime.now().strftime("%H:%M:%S")
    )

    return {
        "public_alert": alert,

        "action_log": (
            state.action_log + [action]
        )
    }
    # =====================================================
# LANGGRAPH WORKFLOW
# =====================================================

workflow = StateGraph(
    CampusEmergencyState
)


workflow.add_node(
    "routing",
    triage_and_routing_agent
)

workflow.add_node(
    "medical",
    medical_response_agent
)

workflow.add_node(
    "security",
    security_agent
)

workflow.add_node(
    "comms",
    communications_agent
)


workflow.set_entry_point(
    "routing"
)

workflow.add_edge(
    "routing",
    "medical"
)

workflow.add_edge(
    "medical",
    "security"
)

workflow.add_edge(
    "security",
    "comms"
)

workflow.add_edge(
    "comms",
    END
)


emergency_orchestrator = (
    workflow.compile()
)


# =====================================================
# FUNCTION USED BY MAIN.PY
# =====================================================

def run_emergency(data: dict):

    incident = Incident(
        **data
    )

    state = CampusEmergencyState(
        incident=incident
    )

    result = emergency_orchestrator.invoke(
        state
    )

    return result