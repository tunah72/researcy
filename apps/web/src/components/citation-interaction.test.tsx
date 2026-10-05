import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ReaderWorkspace } from './reader-workspace';
import * as api from '@/lib/api';

vi.mock('./pdf-reader', () => ({ PdfReader: () => <section aria-label="PDF reader" /> }));
vi.mock('@/lib/api', async importOriginal => ({
  ...await importOriginal<typeof api>(), listConversations:vi.fn(),listMessages:vi.fn(),getCitation:vi.fn(),
}));

const paperId='11111111-1111-4111-8111-111111111111';
const version='22222222-2222-4222-8222-222222222222';
const first:api.ResolvedCitation={citation_id:'33333333-3333-4333-8333-333333333333',paper_id:paperId,
  document_version:version,source_ref:'S1',evidence_quote:'The first exact passage.',page:2,boxes:[[10,20,30,40]],section:null};
const second:api.ResolvedCitation={...first,citation_id:'44444444-4444-4444-8444-444444444444',
  source_ref:'S2',evidence_quote:'The second exact passage.',page:1};
const source:api.ReaderDocument={document_version:version,source_sha256:'a'.repeat(64),pdf_url:'/api/original.pdf',
  outline:[],pages:[0,1].map(page_index=>({page_index,media_box:[0,0,612,792],crop_box:[0,0,612,792],rotation:0}))};
const paper:api.PaperDetailResponse={paper_id:paperId,title:'A public paper',authors:null,year:null,source:'upload',
  stage:'ready',active_version_id:version,source_version:null,screening_warning:null,job_id:'job',retry_revision:0,
  preparation:{state:'complete',reason:null,retryable:false,retry_after_seconds:0},request_id:'request',reader:source};

beforeEach(()=>{
  vi.resetAllMocks();
  window.history.replaceState(null,'','/library/'+paperId);
  Object.defineProperty(window,'innerWidth',{configurable:true,value:1280});
  vi.mocked(api.listConversations).mockResolvedValue({conversations:[{id:'conversation',paper_id:paperId,
    document_version:version,created_at:'2026-10-01T00:00:00Z',updated_at:'2026-10-01T00:00:00Z',last_message:null}],
    next_before:null,request_id:'request'});
  vi.mocked(api.listMessages).mockResolvedValue({messages:[{id:'message',sequence:1,role:'assistant',text:'A supported answer.',
    state:'completed',error_code:null,request_id:'request',created_at:'2026-10-01T00:00:00Z',
    updated_at:'2026-10-01T00:00:00Z',citations:[first,second]}],next_after:null,request_id:'request'});
  vi.mocked(api.getCitation).mockImplementation(async id=>({citation:id===first.citation_id?first:second,request_id:'request'}));
});
afterEach(()=>cleanup());

it('one keyboard activation opens authoritative evidence, and Escape restores focus without losing its page',async()=>{
  const user=userEvent.setup();render(<ReaderWorkspace paper={paper} source={source}/>);
  const button=await screen.findByRole('button',{name:'Citation 1'});
  button.focus();await user.keyboard('{Enter}');
  expect(await screen.findByRole('region',{name:/evidence.*page 2/i})).toBeVisible();
  expect(within(screen.getByRole('log',{name:'Conversation history'})).getByRole('region',{name:/evidence.*page 2/i})).toBeVisible();
  expect(screen.getByText(first.evidence_quote)).toBeVisible();
  const selected=new URL(window.location.href);
  expect(selected.searchParams.get('citation')).toBe(first.citation_id);
  expect(selected.searchParams.get('document_version')).toBe(version);
  expect(selected.searchParams.get('conversation')).toBe('conversation');
  expect(selected.searchParams.get('page')).toBe('2');
  expect(button).toHaveAttribute('aria-expanded','true');
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('region',{name:/evidence/i})).not.toBeInTheDocument();
  expect(button).toHaveFocus();
  expect(new URL(window.location.href).searchParams.get('page')).toBe('2');
  expect(new URL(window.location.href).searchParams.has('citation')).toBe(false);
});

it('a stale accepted-citation request cannot replace a newer selection',async()=>{
  const old=Promise.withResolvers<api.CitationResponse>();
  vi.mocked(api.getCitation).mockImplementation(id=>id===first.citation_id?old.promise:
    Promise.resolve({citation:second,request_id:'request'}));
  const user=userEvent.setup();render(<ReaderWorkspace paper={paper} source={source}/>);
  await user.click(await screen.findByRole('button',{name:'Citation 1'}));
  await user.click(screen.getByRole('button',{name:'Citation 2'}));
  expect(await screen.findByText(second.evidence_quote)).toBeVisible();
  await act(async()=>old.resolve({citation:first,request_id:'request'}));
  expect(screen.queryByText(first.evidence_quote)).not.toBeInTheDocument();
  expect(new URL(window.location.href).searchParams.get('citation')).toBe(second.citation_id);
});

it('refresh/back deep links resolve owned accepted evidence and reject a different immutable version',async()=>{
  window.history.replaceState(null,'','/library/'+paperId+'?document_version='+version+'&conversation=conversation&citation='+first.citation_id+'&page=2');
  render(<ReaderWorkspace paper={paper} source={source}/>);
  expect(await screen.findByText(first.evidence_quote)).toBeVisible();
  window.history.pushState(null,'','?document_version='+version+'&conversation=conversation&citation='+second.citation_id+'&page=1');
  await act(async()=>window.dispatchEvent(new PopStateEvent('popstate')));
  expect(await screen.findByText(second.evidence_quote)).toBeVisible();
  window.history.pushState(null,'','?document_version=foreign-version&citation='+first.citation_id);
  await act(async()=>window.dispatchEvent(new PopStateEvent('popstate')));
  expect(await screen.findByRole('alert')).toHaveTextContent(/unavailable/i);
  expect(screen.queryByText(second.evidence_quote)).not.toBeInTheDocument();
  await waitFor(()=>expect(new URL(window.location.href).searchParams.get('document_version')).toBe('foreign-version'));
});

it('restores the requested owned conversation from a later list page instead of the newest conversation',async()=>{
  window.history.replaceState(null,'','/library/'+paperId+'?document_version='+version+'&conversation=requested');
  const base={paper_id:paperId,document_version:version,created_at:'2026-10-01T00:00:00Z',updated_at:'2026-10-01T00:00:00Z',last_message:null};
  vi.mocked(api.listConversations)
    .mockResolvedValueOnce({conversations:[{...base,id:'newest'}],next_before:'older',request_id:'request'})
    .mockResolvedValueOnce({conversations:[{...base,id:'requested'}],next_before:null,request_id:'request'});
  vi.mocked(api.listMessages).mockImplementation(async id=>({messages:[{
    id:'message',sequence:1,role:'assistant',text:id==='requested'?'Saved selected answer':'Unrelated latest answer',
    state:'completed',error_code:null,request_id:'request',created_at:base.created_at,updated_at:base.updated_at,citations:[],
  }],next_after:null,request_id:'request'}));
  render(<ReaderWorkspace paper={paper} source={source}/>);
  expect(await screen.findByText('Saved selected answer')).toBeVisible();
  expect(screen.queryByText('Unrelated latest answer')).not.toBeInTheDocument();
});

it('Escape after an authenticated deep-link restore focuses the corresponding current citation control',async()=>{
  window.history.replaceState(null,'','/library/'+paperId+'?document_version='+version+'&conversation=conversation&citation='+first.citation_id+'&page=2');
  const user=userEvent.setup();render(<ReaderWorkspace paper={paper} source={source}/>);
  const card=await screen.findByRole('region',{name:/evidence.*page 2/i});
  card.focus();await user.keyboard('{Escape}');
  expect(screen.getByRole('button',{name:'Citation 1'})).toHaveFocus();
  expect(new URL(window.location.href).searchParams.get('page')).toBe('2');
});

it('a deep-link page disagreement cannot display or relocate authoritative accepted evidence',async()=>{
  window.history.replaceState(null,'','/library/'+paperId+'?document_version='+version+'&conversation=conversation&citation='+first.citation_id+'&page=1');
  render(<ReaderWorkspace paper={paper} source={source}/>);
  expect(await screen.findByRole('alert')).toHaveTextContent(/unavailable/i);
  expect(screen.queryByText(first.evidence_quote)).not.toBeInTheDocument();
  expect(new URL(window.location.href).searchParams.get('page')).toBe('1');
});

it('accepted evidence from another owned conversation remains unavailable under the requested conversation',async()=>{
  window.history.replaceState(null,'','/library/'+paperId+'?document_version='+version+'&conversation=conversation&citation='+first.citation_id+'&page=2');
  vi.mocked(api.listMessages).mockResolvedValue({messages:[{id:'other-message',sequence:1,role:'assistant',
    text:'An answer in the requested conversation.',state:'completed',error_code:null,request_id:'request',
    created_at:'2026-10-01T00:00:00Z',updated_at:'2026-10-01T00:00:00Z',citations:[second]}],next_after:null,request_id:'request'});
  render(<ReaderWorkspace paper={paper} source={source}/>);
  expect(await screen.findByRole('alert')).toHaveTextContent(/unavailable/i);
  expect(screen.queryByText(first.evidence_quote)).not.toBeInTheDocument();
});

it('requires current authenticated message membership again when activating a displayed citation', async () => {
  const initial = await api.listMessages('conversation');
  vi.mocked(api.listMessages).mockResolvedValueOnce(initial).mockResolvedValue({
    messages: [{ ...initial.messages[0], citations: [] }], next_after: null, request_id: 'request',
  });
  const user = userEvent.setup();
  render(<ReaderWorkspace paper={paper} source={source} />);
  await user.click(await screen.findByRole('button', { name: 'Citation 1' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/unavailable/i);
  expect(screen.queryByText(first.evidence_quote)).not.toBeInTheDocument();
  expect(new URL(window.location.href).searchParams.has('citation')).toBe(false);
});
