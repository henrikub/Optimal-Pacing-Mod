import json
route_name = 'Park Perimeter Loop'
routes_dict = {}
with open('routes.json', 'r') as file:
    routes_dict = json.load(file)

distance = routes_dict[route_name]['distance']
elevation = routes_dict[route_name]['elevation']

for i in range(len(distance)-1):
    if distance[i] == distance[i+1]:
        print(distance[i])