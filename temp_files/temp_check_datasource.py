from deva.core.namespace import NB

datasources = NB('naja_datasources')
print("Checking for realtime_quant_5s datasource:")

found = False
for key in datasources:
    datasource = datasources[key]
    if isinstance(datasource, dict):
        # 检查name或其他字段
        if 'name' in datasource and datasource['name'] == 'realtime_quant_5s':
            print(f"Found realtime_quant_5s datasource with ID: {key}")
            print(f"Datasource details: {datasource}")
            found = True
        elif 'datasource_name' in datasource and datasource['datasource_name'] == 'realtime_quant_5s':
            print(f"Found realtime_quant_5s datasource with ID: {key}")
            print(f"Datasource details: {datasource}")
            found = True

if not found:
    print("realtime_quant_5s datasource not found")
    print("Available datasources:")
    for key in datasources:
        datasource = datasources[key]
        if isinstance(datasource, dict):
            name = datasource.get('name', datasource.get('datasource_name', 'Unknown'))
            print(f"- {name} (ID: {key})")
