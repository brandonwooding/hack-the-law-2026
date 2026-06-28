from legalgraph import agent


def test_write_command_neo4j_write():
    assert agent.is_write_command("mcp__neo4j__write_neo4j_cypher", {}) is True


def test_write_command_neo4j_read_is_not_write():
    assert agent.is_write_command("mcp__neo4j__read_neo4j_cypher", {}) is False


def test_write_command_ingest_commit():
    cmd = {"command": "legalgraph ingest --jurisdiction eu --id 32024R1689 --commit"}
    assert agent.is_write_command("Bash", cmd) is True


def test_write_command_ingest_plan_is_not_write():
    cmd = {"command": "legalgraph ingest --jurisdiction eu --id 32024R1689 --plan"}
    assert agent.is_write_command("Bash", cmd) is False


def test_write_command_bare_load_link():
    assert agent.is_write_command("Bash", {"command": "legalgraph load"}) is True
    assert agent.is_write_command("Bash", {"command": "legalgraph link"}) is True


def test_write_command_read_bash_is_not_write():
    assert agent.is_write_command("Bash", {"command": "legalgraph ingest --plan ..."}) is False
    assert agent.is_write_command("Read", {"file_path": "x"}) is False


def test_destructive_bash_detach_delete():
    cmd = {"command": "cypher-shell 'MATCH (n) DETACH DELETE n'"}
    assert agent.is_destructive_command("Bash", cmd) is True


def test_destructive_neo4j_write_delete():
    q = {"query": "MATCH (n) DETACH DELETE n"}
    assert agent.is_destructive_command("mcp__neo4j__write_neo4j_cypher", q) is True


def test_sanctioned_ingest_commit_not_destructive():
    cmd = {"command": "legalgraph ingest --jurisdiction eu --id 32024R1689 --commit"}
    assert agent.is_destructive_command("Bash", cmd) is False


def test_plan_and_read_not_destructive():
    assert agent.is_destructive_command("Bash", {"command": "legalgraph ingest --plan"}) is False
    assert agent.is_destructive_command("mcp__neo4j__read_neo4j_cypher", {"query": "MATCH (n) RETURN n"}) is False
