"""
Optimisation d'une tournée journalière (VRPTW à un seul véhicule).

Le "véhicule" est le praticien, le dépôt est la Base (point de départ
et de retour). Chaque arrêt a une fenêtre horaire (fenetre_debut/fin)
et une durée de service (durée de la prestation). Les bilans à
créneau fixe (mardi/vendredi 10h-12h) sont gérés naturellement :
leur fenêtre horaire est simplement très étroite (égale au créneau
imposé), donc le solveur ne peut pas les placer ailleurs.

Le blocage du vendredi après-midi n'est pas géré ici : il doit être
appliqué en amont, en ne proposant tout simplement pas de fenêtre
horaire après 12h30 le vendredi lors de la création des consultations
et en fixant day_end à 12:30 quand on appelle optimize_day un vendredi.
"""
from ortools.constraint_solver import routing_enums_pb2, pywrapcp


def optimize_day(base: dict, stops: list[dict], minutes_matrix: list[list[int]],
                  day_start_minutes: int, day_end_minutes: int, time_limit_seconds: int = 5):
    """
    base: {"duration_minutes": 0}
    stops: [{"id": ..., "duration_minutes": int, "window_start": int, "window_end": int}, ...]
        (fenêtres exprimées en minutes depuis minuit)
    minutes_matrix: matrice carrée [base + stops] x [base + stops], alignée dans cet ordre
    Retourne None si aucune solution trouvée (contraintes infaisables),
    sinon la liste ordonnée des arrêts avec heure d'arrivée en minutes.
    """
    locations = [base] + stops
    n = len(locations)

    manager = pywrapcp.RoutingIndexManager(n, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        service = locations[from_node].get("duration_minutes", 0)
        return minutes_matrix[from_node][to_node] + service

    transit_callback_index = routing.RegisterTransitCallback(time_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    routing.AddDimension(
        transit_callback_index,
        120,        # attente max autorisée entre deux arrêts (minutes)
        24 * 60,    # horizon max de la journée
        False,
        "Time",
    )
    time_dimension = routing.GetDimensionOrDie("Time")

    for idx, loc in enumerate(locations):
        index = manager.NodeToIndex(idx)
        start = loc.get("window_start", day_start_minutes)
        end = loc.get("window_end", day_end_minutes)
        time_dimension.CumulVar(index).SetRange(start, end)

    depot_index = manager.NodeToIndex(0)
    time_dimension.CumulVar(depot_index).SetRange(day_start_minutes, day_end_minutes)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.FromSeconds(time_limit_seconds)

    solution = routing.SolveWithParameters(search_parameters)
    if not solution:
        return None

    ordered = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        arrival = solution.Min(time_dimension.CumulVar(index))
        ordered.append({"node": node, "arrival_minutes": arrival})
        index = solution.Value(routing.NextVar(index))
    node = manager.IndexToNode(index)  # retour au dépôt
    arrival = solution.Min(time_dimension.CumulVar(index))
    ordered.append({"node": node, "arrival_minutes": arrival})

    return ordered
