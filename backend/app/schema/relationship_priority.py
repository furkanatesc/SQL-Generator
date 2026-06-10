from app.schema.schema_contract import RelationshipType

RELATIONSHIP_TYPE_PRIORITY = {
    RelationshipType.EXPLICIT: 100,
    RelationshipType.CUSTOM: 90,
    RelationshipType.IMPLICIT: 60,
    RelationshipType.IMPLICIT_FUZZY: 40,
}
