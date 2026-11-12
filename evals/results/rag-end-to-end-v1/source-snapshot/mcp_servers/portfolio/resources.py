def case_resource(service, tenant_id: str, id: str) -> str:
    return service.case_study(tenant_id, id).model_dump_json()


def proposal_resource(service, tenant_id: str, id: str) -> str:
    item = service.case_study(tenant_id, id)
    if item.type != "proposal":
        raise ValueError("This source is not a past proposal")
    return item.model_dump_json()
