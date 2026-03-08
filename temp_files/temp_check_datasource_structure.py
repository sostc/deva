from deva.core.namespace import NB

datasources = NB('naja_datasources')
print("Datasource structure:")
for key in datasources:
    datasource = datasources[key]
    print(f"Key: {key}")
    print(f"Type: {type(datasource)}")
    if isinstance(datasource, dict):
        print(f"Keys: {list(datasource.keys())}")
        # 打印所有值，看看哪些字段可能包含数据源名称
        for k, v in datasource.items():
            print(f"  {k}: {v}")
    print()
