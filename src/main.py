from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage
from src.state import WaymaxState
from src.agents.supervisor import supervisor_node
from src.agents.sourcing import sourcing_node
from src.agents.optimization import optimizer_node # 1. Updated the import name here

# Initialize workflow with State
workflow = StateGraph(WaymaxState)

# Add nodes
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("sourcing", sourcing_node)
workflow.add_node("optimization", optimizer_node) # 2. Updated the function name here

# Set entry point
workflow.set_entry_point("supervisor")

# Add conditional edge from supervisor
workflow.add_conditional_edges(
    "supervisor",
    lambda state: state.get("next_node", "end"),
    {
        "sourcing": "sourcing",
        "end": END
    }
)

# 3. Edge from sourcing to optimization
workflow.add_edge("sourcing", "optimization")

# 4. Edge from optimization to END
workflow.add_edge("optimization", END)

# Compile the workflow
app = workflow.compile()

if __name__ == "__main__":
    # Test with a mock state containing a human message
# Test with a mock state containing all required variables
    test_state = {
        "chat_history": [HumanMessage(content="I want to book a trip from Turin to Tokyo from August 1st to August 8th with a budget of 2000")],
        "origin": "TRN",           # Turin Airport
        "destination": "NRT",      # Narita International Airport
        "max_budget": 2500.00,
        "travel_dates": "2027-08-01 to 2027-08-08",
        "raw_flight_data": [],
        "raw_hotel_data": [],
        "final_itinerary": None,
        "next_node": ""
    }

    print("Invoking graph...")
    final_output = app.invoke(test_state)
    print("\nFinal State:")
    import pprint
    pprint.pprint(final_output)