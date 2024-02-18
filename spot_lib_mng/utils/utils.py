def remove_metadata(db_item, with_mongo_id=False):
    if 'modified_at' in db_item:
        del db_item['modified_at']
    if 'modified_by' in db_item:
        del db_item['modified_by']
    if 'created_at' in db_item:
        del db_item['created_at']
    if 'created_by' in db_item:
        del db_item['created_by']

    if with_mongo_id and '_id' in db_item:
        del db_item['_id']
    return db_item


def convert_query_param_string(incoming: str):
    return incoming.replace(' ', '+').replace(',', '%2C')
