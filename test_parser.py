import os, tempfile
from tracking_parser import find_tracking_numbers, is_delivered, guess_carrier
from db import DB

def test_ups():
    assert find_tracking_numbers("Your UPS tracking: 1Z999AA10123456784") == [("1Z999AA10123456784","UPS")]
def test_ups_in_link():
    t = '<a href="https://www.ups.com/track?tracknum=1Z999AA10123456784">Track</a>'
    from mail_scanner import _html_to_text
    assert ("1Z999AA10123456784","UPS") in find_tracking_numbers(_html_to_text(t))
def test_amazon():
    assert find_tracking_numbers("Amazon shipped TBA123456789012") == [("TBA123456789012","Amazon")]
def test_usps():
    assert find_tracking_numbers("USPS tracking number 9400111899223344556677") == [("9400111899223344556677","USPS")]
def test_fedex():
    assert find_tracking_numbers("FedEx shipment tracking 771234567890") == [("771234567890","FedEx")]
def test_no_false_positive():
    assert find_tracking_numbers("Order #123456789012 total $20, call 800 555 1234") == []
def test_delivered():
    assert is_delivered("Delivered, In/At Mailbox")
    assert is_delivered("DELIVERED")
    assert not is_delivered("OUT FOR DELIVERY TODAY")
    assert not is_delivered("Delivery attempted")
    assert not is_delivered("Will be delivered tomorrow")
def test_guess():
    assert guess_carrier("1z4x67420389975875") == "UPS"
    assert guess_carrier("771234567890") == "FedEx"
def test_db():
    d = DB(os.path.join(tempfile.mkdtemp(), "t.db"))
    assert d.add("A1","UPS","x"); assert not d.add("A1","UPS","x")
    d.add("B2","UPS","y"); d.update_status("B2","Delivered","NY","t",True)
    assert d.active()[0]["number"] == "B2"
    assert [r["number"] for r in d.to_check()] == ["A1"]
    d.archive("B2"); assert len(d.active()) == 1 and not d.add("B2","UPS","y")
