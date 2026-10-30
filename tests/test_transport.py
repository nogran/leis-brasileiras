import pytest
import requests

from leis_brasileiras import transport

URL='https://www.planalto.gov.br/ccivil_03/leis/l9099.htm'


class Response:
    def __init__(self,status=200,mime='text/html',body=b'<html>example</html>'):
        self.status_code=status
        self.headers={'Content-Type':mime}
        self.body=body
    def __enter__(self):
        return self
    def __exit__(self,*args):
        pass
    def raise_for_status(self):
        if self.status_code>=400:
            raise requests.HTTPError('source failure')
    def iter_content(self,chunk_size):
        yield self.body


class Session:
    def __init__(self,responses):
        self.responses=iter(responses)
        self.headers={}
        self.calls=[]
        self.trust_env=True
    def __enter__(self):
        return self
    def __exit__(self,*args):
        pass
    def get(self,url,**kwargs):
        self.calls.append(kwargs)
        response=next(self.responses)
        if isinstance(response,Exception):
            raise response
        return response


def test_retry_is_bounded_and_ambient_credentials_disabled(monkeypatch):
    session=Session([requests.ConnectionError('offline'),Response()])
    monkeypatch.setattr(transport.requests,'Session',lambda:session)
    monkeypatch.setattr(transport,'sleep',lambda seconds:None)
    assert transport.fetch_html(URL)==b'<html>example</html>'
    assert len(session.calls)==2
    assert session.trust_env is False
    assert session.headers["User-Agent"] == transport.USER_AGENT
    assert "leis-brasileiras/" in transport.USER_AGENT
    assert all(call['allow_redirects'] is False and call['stream'] for call in session.calls)


@pytest.mark.parametrize('response',[Response(302),Response(200,'application/pdf'),Response(body=b''),Response(body=b'x'*101)])
def test_redirect_mime_empty_and_volume_refused(monkeypatch,response):
    monkeypatch.setattr(transport.requests,'Session',lambda:Session([response]))
    monkeypatch.setattr(transport,'MAX_HTML_BYTES',100)
    with pytest.raises(ValueError):
        transport.fetch_html(URL)


def test_two_failures_do_not_loop_forever(monkeypatch):
    session=Session([requests.Timeout('one'),requests.Timeout('two')])
    monkeypatch.setattr(transport.requests,'Session',lambda:session)
    monkeypatch.setattr(transport,'sleep',lambda seconds:None)
    with pytest.raises(requests.Timeout):
        transport.fetch_html(URL)
    assert len(session.calls)==2


def test_sessions_are_owned_per_fetch(monkeypatch):
    sessions=[]
    def create():
        session=Session([Response()]); sessions.append(session); return session
    monkeypatch.setattr(transport.requests,'Session',create)
    transport.fetch_html(URL); transport.fetch_html(URL)
    assert len(sessions)==2 and sessions[0] is not sessions[1]
