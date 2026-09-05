"""Each person gets their own switch, and cannot see anybody else's."""
import io


def test_each_person_has_their_own_switch(world):
    sam = world.make("sam", settings=dict(owner_email="sam@example.com",
                                          recipient_email="sams-friend@example.com",
                                          smtp_host="smtp.example.com", smtp_from="sam@example.com",
                                          base_url="http://departed.test", reminder_count="3"))
    world.switches.store(sam).set("letter", "Sam's letter")
    charlie_files = world.archive
    charlie_files.mkdir(parents=True, exist_ok=True)
    (charlie_files / "charlie.gpg").write_bytes(b"c")
    sam_files = world.switches.archive_dir(sam)
    sam_files.mkdir(parents=True, exist_ok=True)
    (sam_files / "sam.gpg").write_bytes(b"s")

    for _ in range(21 * 24):
        world.clock.advance(hours=1)
        world.tick()

    to_recipients = {m["to"]: m for m in world.mailer.sent if m["attachment"]}
    assert set(to_recipients) == {"them@example.com", "sams-friend@example.com"}
    assert to_recipients["them@example.com"]["attachment"][0] == "charlie.gpg"
    assert to_recipients["sams-friend@example.com"]["attachment"][0] == "sam.gpg"
    assert to_recipients["sams-friend@example.com"]["body"].startswith("Sam's letter")


def test_one_person_cannot_see_another(world):
    sam = world.make("sam", settings=dict(owner_email="sam@example.com"))
    world.switches.store(sam).set("letter", "Sam's private letter")
    (world.switches.archive_dir(sam)).mkdir(parents=True, exist_ok=True)
    (world.switches.archive_dir(sam) / "sams-file.gpg").write_bytes(b"s")

    page = world.client.get("/settings").get_data(as_text=True)
    assert "Sam's private letter" not in page
    assert "sams-file.gpg" not in page
    assert "sam@example.com" not in page


def test_one_person_cannot_delete_anothers_file(world):
    sam = world.make("sam")
    sam_dir = world.switches.archive_dir(sam)
    sam_dir.mkdir(parents=True, exist_ok=True)
    (sam_dir / "sams-file.gpg").write_bytes(b"s")
    world.client.post("/files/delete", data={"name": "sams-file.gpg"})
    assert (sam_dir / "sams-file.gpg").exists()


def test_an_admin_can_add_and_remove_people(world):
    c = world.client
    c.post("/people", data={"username": "sam", "password": "sams-long-password",
                            "confirm": "sams-long-password"})
    sam = world.db.user_by_name("sam")
    assert sam and not sam.is_admin
    assert world.client_for("sam", "sams-long-password").get("/").status_code == 200

    sam_dir = world.switches.archive_dir(sam.id)
    sam_dir.mkdir(parents=True, exist_ok=True)
    (sam_dir / "sams-file.gpg").write_bytes(b"s")

    c.post("/people/delete", data={"user_id": sam.id})
    assert world.db.user_by_name("sam") is None
    assert not sam_dir.exists()
    assert world.db.recent_events(sam.id) == []


def test_an_ordinary_person_cannot_reach_the_people_page(world):
    world.db.set_user_admin(world.user_id, False)
    assert world.client.get("/people").status_code == 403
    assert world.client.post("/people", data={"username": "x", "password": "y" * 12,
                                              "confirm": "y" * 12}).status_code == 403


def test_you_cannot_remove_yourself_or_the_last_admin(world):
    r = world.client.post("/people/delete", data={"user_id": world.user_id})
    assert "cannot+remove+your+own" in r.headers["Location"]
    assert world.db.user(world.user_id) is not None


def test_duplicate_usernames_are_refused(world):
    r = world.client.post("/people", data={"username": "Charlie", "password": "another-long-one",
                                           "confirm": "another-long-one"})
    assert "already" in r.headers["Location"]
    assert len(world.db.users()) == 1
