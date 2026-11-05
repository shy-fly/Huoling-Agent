from app.rag.experiment_retrieval import retrieveExperimentEvidence


def test_retrieval_fuses_distinct_queries_and_deduplicates():
    queries = []
    def search(query, top_k):
        queries.append(query)
        if len(queries) == 1:
            return [{"id": 1}, {"id": 2}]
        return [{"id": 2}, {"id": 3}]

    result = retrieveExperimentEvidence("Does ammonia reduce methane production?", 2, search=search)
    assert len(set(queries)) == 4
    assert [chunk["id"] for chunk in result] == [2, 3]
