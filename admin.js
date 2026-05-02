const API='/api';
const token=localStorage.getItem('vs_token');
const role=localStorage.getItem('vs_role');
const adminName=localStorage.getItem('vs_name')||'Admin';
if(!token||(role!=='super_admin'&&role!=='election_officer'))window.location.href='index.html';

let allElections=[],allUsers=[],allLogs=[];
let dashChart=null,resBarInst=null,resPieInst=null,hourlyInst=null,genderInst=null;
let currentResElection=null,selectedUserId=null;

document.addEventListener('DOMContentLoaded',()=>{
  document.getElementById('adminName').textContent=adminName;
  document.getElementById('adminRole').textContent=role==='super_admin'?'⭐ Super Admin':'Election Officer';
  document.getElementById('adminAvatar').textContent=adminName.charAt(0).toUpperCase();
  restoreTheme();loadDashboard();
});

function toggleTheme(){const d=document.documentElement;const dark=d.getAttribute('data-theme')==='dark';d.setAttribute('data-theme',dark?'':'dark');document.getElementById('themeBtn').textContent=dark?'🌙 Dark':'☀️ Light';localStorage.setItem('vs_theme',dark?'light':'dark');}
function restoreTheme(){if(localStorage.getItem('vs_theme')==='dark'){document.documentElement.setAttribute('data-theme','dark');document.getElementById('themeBtn').textContent='☀️ Light';}}
function auth(){return{'Content-Type':'application/json','Authorization':`Bearer ${token}`};}
function toast(msg,type='info'){const t=document.getElementById('toast');t.textContent=msg;t.className=`toast toast-${type}`;setTimeout(()=>t.classList.add('hidden'),4000);}
function openModal(id){document.getElementById(id).classList.remove('hidden');}
function closeModal(id){document.getElementById(id).classList.add('hidden');}
async function logout(){await fetch(`${API}/auth/logout`,{method:'POST',headers:auth()});localStorage.clear();window.location.href='index.html';}

const viewMeta={
  dashboard:['Dashboard','Election management overview'],
  elections:['Elections','Create and manage elections'],
  candidates:['Candidates','Add or remove candidates'],
  users:['Voter Management','View and manage registered voters'],
  results:['Results','View results and export reports'],
  analytics:['Analytics','Detailed voting analytics'],
  announcements:['Announcements','Post updates to voters'],
  anomalies:['AI Anomaly Detection','Suspicious pattern alerts'],
  audit:['Audit Logs','Complete system activity trail'],
};
function showView(v){
  document.querySelectorAll('.view').forEach(el=>el.classList.add('hidden'));
  document.querySelectorAll('.nav-link').forEach(el=>el.classList.remove('active'));
  document.getElementById(`view-${v}`).classList.remove('hidden');
  document.getElementById(`nav-${v}`).classList.add('active');
  document.getElementById('viewTitle').textContent=viewMeta[v][0];
  document.getElementById('viewSub').textContent=viewMeta[v][1];
  const loaders={elections:loadElections,candidates:loadCandDropdowns,users:loadUsers,results:loadResDropdown,analytics:loadAnalyticsDropdown,announcements:loadAnnouncements,anomalies:loadAnomalies,audit:loadAuditLogs};
  if(loaders[v])loaders[v]();
}

// ── DASHBOARD ──────────────────────────────────────
async function loadDashboard(){
  try{
    const [elRes,turnRes,anomRes]=await Promise.all([
      fetch(`${API}/elections`,{headers:auth()}),
      fetch(`${API}/admin/turnout`,{headers:auth()}),
      fetch(`${API}/ai/anomalies`,{headers:auth()})
    ]);
    allElections=(await elRes.json()).elections||[];
    const{turnout,total_registered}=await turnRes.json();
    const{count}=await anomRes.json();
    const totalVotes=turnout.reduce((s,t)=>s+t.votes_cast,0);
    document.getElementById('d-elections').textContent=allElections.length;
    document.getElementById('d-voters').textContent=total_registered;
    document.getElementById('d-votes').textContent=totalVotes;
    document.getElementById('d-anomalies').textContent=count;
    document.getElementById('turnoutList').innerHTML=turnout.map(t=>{
      const pct=total_registered>0?Math.round(t.votes_cast/total_registered*100):0;
      return`<div class="turnout-item"><div class="turnout-label"><span>${t.title} <span class="badge badge-${t.status==='active'?'success':t.status==='ended'?'secondary':'warning'}">${t.status}</span></span><span>${t.votes_cast} (${pct}%)</span></div><div class="progress"><div class="progress-fill" style="width:${pct}%"></div></div></div>`;
    }).join('');
    const active=turnout.filter(t=>t.status==='active');
    if(dashChart)dashChart.destroy();
    if(active.length){
      dashChart=new Chart(document.getElementById('dashChart'),{
        type:'bar',
        data:{labels:active.map(t=>t.title.substring(0,20)),datasets:[{label:'Votes',data:active.map(t=>t.votes_cast),backgroundColor:'#1a3a6b'}]},
        options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true}}}
      });
    }
  }catch(e){toast('Dashboard load failed','error');}
}

// ── ELECTIONS ──────────────────────────────────────
async function loadElections(){
  const res=await fetch(`${API}/elections`,{headers:auth()});
  allElections=(await res.json()).elections||[];
  const turnRes=await fetch(`${API}/admin/turnout`,{headers:auth()});
  const{turnout}=await turnRes.json();
  const voteMap=Object.fromEntries(turnout.map(t=>[t.election_id,t.votes_cast]));
  document.getElementById('electionsTable').innerHTML=allElections.map(e=>`
    <tr>
      <td>${e.election_id}</td>
      <td><strong>${e.title}</strong><br><small style="color:var(--text-muted)">${e.constituency}</small></td>
      <td>${e.constituency}</td>
      <td>${new Date(e.start_date).toLocaleDateString()}</td>
      <td>${new Date(e.end_date).toLocaleDateString()}</td>
      <td><span class="badge badge-${e.status==='active'?'success':e.status==='upcoming'?'warning':'secondary'}">${e.status}</span></td>
      <td>${voteMap[e.election_id]||0}</td>
      <td style="display:flex;gap:.4rem;flex-wrap:wrap">
        <button class="btn btn-outline btn-sm" onclick="editElection(${e.election_id})">✏️</button>
        ${e.status === 'active' ? `<button class="btn btn-danger btn-sm" onclick="quickEndElection(${e.election_id})" style="background:#ef4444;border-color:#ef4444">🏁 End</button>` : ''}
        <button class="btn btn-danger btn-sm" onclick="deleteElection(${e.election_id})">🗑️</button>
      </td>
    </tr>`).join('');
}
async function quickEndElection(id) {
  if (!confirm('Are you sure you want to END this election? No more votes will be allowed and results will be published.')) return;
  const res = await fetch(`${API}/admin/elections/${id}`, {
    method: 'PUT',
    headers: auth(),
    body: JSON.stringify({ status: 'ended' })
  });
  const data = await res.json();
  toast(res.ok ? 'Election Ended and Results Finalized!' : data.error, res.ok ? 'success' : 'error');
  if (res.ok) loadElections();
}
function openElectionModal(){document.getElementById('editElId').value='';document.getElementById('elModalTitle').textContent='Create Election';['el-title','el-desc'].forEach(id=>document.getElementById(id).value='');openModal('electionModal');}
function editElection(id){
  const e=allElections.find(x=>x.election_id===id);if(!e)return;
  document.getElementById('editElId').value=id;
  document.getElementById('elModalTitle').textContent='Edit Election';
  document.getElementById('el-title').value=e.title;
  document.getElementById('el-desc').value=e.description||'';
  document.getElementById('el-const').value=e.constituency;
  document.getElementById('el-status').value=e.status;
  document.getElementById('el-start').value=e.start_date.replace(' ','T').substring(0,16);
  document.getElementById('el-end').value=e.end_date.replace(' ','T').substring(0,16);
  openModal('electionModal');
}
async function saveElection(){
  const btn = document.querySelector('#electionModal .btn-primary');
  btn.disabled = true;
  btn.innerHTML = 'Saving...';
  
  const editId=document.getElementById('editElId').value;
  const body={title:document.getElementById('el-title').value.trim(),description:document.getElementById('el-desc').value,constituency:document.getElementById('el-const').value,status:document.getElementById('el-status').value,start_date:document.getElementById('el-start').value.replace('T',' '),end_date:document.getElementById('el-end').value.replace('T',' ')};
  if(!body.title||!body.start_date||!body.end_date){
    btn.disabled = false; btn.innerHTML = 'Save Election';
    return toast('Title and dates required','error');
  }
  const url=editId?`${API}/admin/elections/${editId}`:`${API}/admin/elections`;
  const method=editId?'PUT':'POST';
  try {
    const res=await fetch(url,{method,headers:auth(),body:JSON.stringify(body)});
    const data=await res.json();
    toast(res.ok?data.message:data.error,res.ok?'success':'error');
    if(res.ok){closeModal('electionModal');loadElections();}
  } catch(e) { toast('Network error','error'); }
  btn.disabled = false; btn.innerHTML = 'Save Election';
}
async function deleteElection(id){
  if(!confirm('Delete this election? All votes will be lost.'))return;
  // Optimistic UI: Hide the row immediately
  const row = document.querySelector(`button[onclick="deleteElection(${id})"]`)?.closest('tr');
  if(row) row.style.opacity = '0.3';
  
  try {
    const res=await fetch(`${API}/admin/elections/${id}`,{method:'DELETE',headers:auth()});
    const data=await res.json();
    toast(res.ok?data.message:data.error,res.ok?'success':'error');
    if(res.ok) {
        if(row) row.remove();
        loadElections();
    } else {
        if(row) row.style.opacity = '1';
    }
  } catch(e) {
    if(row) row.style.opacity = '1';
    toast('Delete failed','error');
  }
}

// ── CANDIDATES ─────────────────────────────────────
async function loadCandDropdowns(){
  const res=await fetch(`${API}/elections`,{headers:auth()});
  allElections=(await res.json()).elections||[];
  const opts=allElections.map(e=>`<option value="${e.election_id}">${e.title}</option>`).join('');
  document.getElementById('candFilter').innerHTML='<option value="">— Select Election —</option>'+opts;
  document.getElementById('cand-eid').innerHTML=opts;
}
async function loadCandidates(){
  const eid=document.getElementById('candFilter').value;
  if(!eid){document.getElementById('candidateGrid').innerHTML='';return;}
  const res=await fetch(`${API}/candidates?election_id=${eid}`,{headers:auth()});
  const candidates=(await res.json()).candidates||[];
  document.getElementById('candidateGrid').innerHTML=candidates.length?candidates.map(c=>`
    <div class="candidate-card">
      <div class="candidate-avatar">${c.photo_url ? `<img src="${c.photo_url}" style="width:100%;height:100%;object-fit:cover;border-radius:50%">` : c.name.charAt(0)}</div>
      <div class="candidate-name">${c.name}</div>
      <div class="candidate-party">🏛️ ${c.party}</div>
      <div style="font-size:.72rem;color:var(--text-muted);margin:.3rem 0">📍 ${c.constituency}</div>
      <div class="candidate-manifesto">${c.manifesto||''}</div>
      <button class="btn btn-danger btn-sm" style="margin-top:.75rem;width:100%" onclick="deleteCandidate(${c.candidate_id})">🗑️ Remove</button>
    </div>`).join(''):'<p style="color:var(--text-muted);grid-column:1/-1">No candidates yet. Add one above.</p>';
}
async function saveCandidate(){
  const btn = document.querySelector('#candidateModal .btn-primary');
  btn.disabled = true;
  btn.innerHTML = 'Processing...';

  const editId=document.getElementById('editCandId').value;
  const body={election_id:document.getElementById('cand-el').value,name:document.getElementById('cand-name').value.trim(),party:document.getElementById('cand-party').value.trim(),constituency:document.getElementById('cand-const').value,manifesto:document.getElementById('cand-manifesto').value};
  if(!body.election_id||!body.name||!body.party){
    btn.disabled = false; btn.innerHTML = 'Save Candidate';
    return toast('Election, Name and Party required','error');
  }
  const url=editId?`${API}/admin/candidates/${editId}`:`${API}/admin/candidates`;
  const method=editId?'PUT':'POST';
  try {
    const res=await fetch(url,{method,headers:auth(),body:JSON.stringify(body)});
    const data=await res.json();
    toast(res.ok?data.message:data.error,res.ok?'success':'error');
    if(res.ok){closeModal('candidateModal');loadCandidates();}
  } catch(e) { toast('Error saving candidate','error'); }
  btn.disabled = false; btn.innerHTML = 'Save Candidate';
}
async function deleteCandidate(id){
  if(!confirm('Remove this candidate?'))return;
  const res=await fetch(`${API}/admin/candidates/${id}`,{method:'DELETE',headers:auth()});
  const data=await res.json();
  toast(res.ok?data.message:data.error,res.ok?'success':'error');
  if(res.ok)loadCandidates();
}

// ── USERS ───────────────────────────────────────────
async function loadUsers(){
  const res=await fetch(`${API}/admin/users`,{headers:auth()});
  allUsers=(await res.json()).users||[];
  renderUsers(allUsers);
}
function renderUsers(users){
  const empty=document.getElementById('usersEmpty');
  if(!users.length){document.getElementById('usersTable').innerHTML='';empty.classList.remove('hidden');return;}
  empty.classList.add('hidden');
  document.getElementById('usersTable').innerHTML=users.map(u=>`
    <tr>
      <td><code style="font-size:.78rem">${u.voter_id}</code></td>
      <td><strong>${u.name}</strong></td>
      <td style="font-size:.82rem">${u.email}</td>
      <td style="font-size:.82rem">${u.phone||'—'}</td>
      <td>${u.constituency}</td>
      <td style="font-size:.78rem">${u.aadhaar_id?'✅ '+u.aadhaar_id.substring(0,4)+'********':'—'}</td>
      <td style="font-size:.78rem">${u.govt_voter_id||'—'}</td>
      <td style="font-size:.78rem;white-space:nowrap">${new Date(u.created_at).toLocaleDateString()}</td>
      <td>
        <button class="btn btn-outline btn-sm" onclick="viewUser('${u.voter_id}')">👁</button>
        ${role==='super_admin'?`<button class="btn btn-danger btn-sm" onclick="confirmDeleteUser('${u.voter_id}','${u.name.replace(/'/g,"\\'")}')">🗑️</button>`:''}
      </td>
    </tr>`).join('');
}
function filterUsers(){
  const q=document.getElementById('userSearch').value.toLowerCase();
  renderUsers(allUsers.filter(u=>u.name.toLowerCase().includes(q)||u.email.toLowerCase().includes(q)||(u.voter_id||'').toLowerCase().includes(q)));
}
function viewUser(id){
  const u=allUsers.find(x=>x.voter_id===id);if(!u)return;
  selectedUserId=id;
  document.getElementById('userModalBody').innerHTML=`
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:.75rem;font-size:.88rem">
      <div><div style="color:var(--text-muted);font-size:.72rem;text-transform:uppercase">Full Name</div><div style="font-weight:600">${u.name}</div></div>
      <div><div style="color:var(--text-muted);font-size:.72rem;text-transform:uppercase">Voter ID</div><div style="font-weight:600;font-family:monospace">${u.voter_id}</div></div>
      <div><div style="color:var(--text-muted);font-size:.72rem;text-transform:uppercase">Email</div><div>${u.email}</div></div>
      <div><div style="color:var(--text-muted);font-size:.72rem;text-transform:uppercase">Phone</div><div>${u.phone||'Not provided'}</div></div>
      <div><div style="color:var(--text-muted);font-size:.72rem;text-transform:uppercase">Constituency</div><div>${u.constituency}</div></div>
      <div><div style="color:var(--text-muted);font-size:.72rem;text-transform:uppercase">Aadhaar</div><div>${u.aadhaar_id||'Not provided'}</div></div>
      <div><div style="color:var(--text-muted);font-size:.72rem;text-transform:uppercase">Govt Voter ID</div><div>${u.govt_voter_id||'Not provided'}</div></div>
      <div><div style="color:var(--text-muted);font-size:.72rem;text-transform:uppercase">Registered</div><div>${new Date(u.created_at).toLocaleString()}</div></div>
    </div>`;
  if(role!=='super_admin')document.getElementById('deleteUserBtn').style.display='none';
  openModal('userModal');
}
function confirmDeleteUser(id,name){
  selectedUserId=id;
  viewUser(id);
}
async function deleteUserConfirm(){
  if(!selectedUserId)return;
  if(!confirm(`Permanently delete this voter and all their vote data? This CANNOT be undone.`))return;
  const res=await fetch(`${API}/admin/users/${selectedUserId}`,{method:'DELETE',headers:auth()});
  const data=await res.json();
  if(res.ok){closeModal('userModal');toast(data.message,'success');loadUsers();}
  else toast(data.error,'error');
  selectedUserId=null;
}

// ── RESULTS ─────────────────────────────────────────
async function loadResDropdown(){
  const res=await fetch(`${API}/elections`,{headers:auth()});
  allElections=(await res.json()).elections||[];
  document.getElementById('resSelect').innerHTML='<option value="">— Select Election —</option>'+allElections.map(e=>`<option value="${e.election_id}">${e.title} (${e.status})</option>`).join('');
  document.getElementById('resultsPanel').classList.add('hidden');
}
async function loadResults(eid){
  if(!eid){document.getElementById('resultsPanel').classList.add('hidden');return;}
  currentResElection=eid;
  document.getElementById('resultsPanel').classList.remove('hidden');
  const[rRes,sumRes]=await Promise.all([
    fetch(`${API}/results/${eid}`,{headers:auth()}),
    fetch(`${API}/ai/summarize/${eid}`,{headers:auth()})
  ]);
  const{results,total_votes}=await rRes.json();
  const{summary}=await sumRes.json();
  const colors=['#1a3a6b','#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899'];
  if(results.length){
    const w=results[0];
    document.getElementById('winnerCard').innerHTML=`<div class="winner-card"><div class="winner-trophy">🏆</div><div><div style="font-size:.75rem;opacity:.75;text-transform:uppercase">Winner</div><div class="winner-name">${w.candidate_name}</div><div class="winner-party">${w.party}</div><div class="winner-votes">${w.total_votes} votes · ${w.percentage}%</div></div><div style="margin-left:auto;text-align:right"><div style="font-size:.78rem;opacity:.75">Total Votes Cast</div><div style="font-size:2.2rem;font-weight:800">${total_votes}</div></div></div>`;
  }
  if(resBarInst)resBarInst.destroy();if(resPieInst)resPieInst.destroy();
  resBarInst=new Chart(document.getElementById('resBar'),{type:'bar',data:{labels:results.map(r=>r.candidate_name),datasets:[{label:'Votes',data:results.map(r=>r.total_votes),backgroundColor:colors}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true}}}});
  resPieInst=new Chart(document.getElementById('resPie'),{type:'pie',data:{labels:results.map(r=>r.candidate_name),datasets:[{data:results.map(r=>r.percentage),backgroundColor:colors}]},options:{responsive:true,maintainAspectRatio:false}});
  document.getElementById('resTable').innerHTML=results.map((r,i)=>`<tr><td>${i+1}</td><td><strong>${r.candidate_name}</strong>${i===0?' 🏆':''}</td><td>${r.party}</td><td>${r.total_votes}</td><td>${r.percentage}%</td><td style="min-width:100px"><div class="progress"><div class="progress-fill" style="width:${r.percentage}%"></div></div></td></tr>`).join('');
  document.getElementById('aiSummary').textContent=summary;
}
function exportCSV(){
  if(!currentResElection)return toast('Select an election first','error');
  fetch(`${API}/admin/export/csv/${currentResElection}`,{headers:auth()}).then(r=>r.blob()).then(b=>{const u=URL.createObjectURL(b);const a=document.createElement('a');a.href=u;a.download='results.csv';a.click();});
}
function exportPDF(){
  if(!currentResElection)return toast('Select an election first','error');
  fetch(`${API}/admin/export/pdf/${currentResElection}`,{headers:auth()}).then(r=>r.text()).then(h=>{const w=window.open('','_blank');w.document.write(h);w.document.close();});
}

// ── ANALYTICS ───────────────────────────────────────
async function loadAnalyticsDropdown(){
  const res=await fetch(`${API}/elections`,{headers:auth()});
  allElections=(await res.json()).elections||[];
  document.getElementById('analyticsSelect').innerHTML='<option value="">— Select Election —</option>'+allElections.map(e=>`<option value="${e.election_id}">${e.title}</option>`).join('');
  document.getElementById('analyticsPanel').classList.add('hidden');
}
async function loadAnalytics(eid){
  if(!eid){document.getElementById('analyticsPanel').classList.add('hidden');return;}
  document.getElementById('analyticsPanel').classList.remove('hidden');
  const res=await fetch(`${API}/admin/analytics/${eid}`,{headers:auth()});
  const{hourly,gender,constituency}=await res.json();
  if(hourlyInst)hourlyInst.destroy();
  hourlyInst=new Chart(document.getElementById('hourlyChart'),{type:'line',data:{labels:hourly.map(h=>h.hour),datasets:[{label:'Votes',data:hourly.map(h=>h.cnt),borderColor:'#1a3a6b',backgroundColor:'rgba(26,58,107,.1)',fill:true,tension:.4}]},options:{responsive:true,maintainAspectRatio:false,scales:{y:{beginAtZero:true}}}});
  if(genderInst)genderInst.destroy();
  genderInst=new Chart(document.getElementById('genderChart'),{type:'doughnut',data:{labels:gender.map(g=>g.gender||'Unknown'),datasets:[{data:gender.map(g=>g.cnt),backgroundColor:['#3b82f6','#ec4899','#10b981']}]},options:{responsive:true,maintainAspectRatio:false}});
  document.getElementById('constList').innerHTML=constituency.length?constituency.map(c=>`<div class="turnout-item"><div class="turnout-label"><span>${c.constituency}</span><span>${c.cnt} votes</span></div><div class="progress"><div class="progress-fill" style="width:${Math.min(100,c.cnt*10)}%"></div></div></div>`).join(''):'<p style="color:var(--text-muted)">No constituency data yet.</p>';
}

// ── ANNOUNCEMENTS ────────────────────────────────────
async function loadAnnouncements(){
  const res=await fetch(`${API}/admin/announcements`,{headers:auth()});
  const anns=(await res.json()).announcements||[];
  document.getElementById('annList').innerHTML=anns.length?anns.map(a=>`
    <div class="card" style="margin-bottom:.75rem;border-left:4px solid ${a.priority==='high'?'#ef4444':'#3b82f6'}">
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <div>
          <div style="font-weight:700;margin-bottom:.3rem">${a.title}</div>
          <div style="font-size:.85rem;color:var(--text-muted);margin-bottom:.5rem">${a.body}</div>
          <div style="font-size:.72rem;color:var(--text-light)">${new Date(a.created_at).toLocaleString()} · by ${a.admin_id}</div>
        </div>
        <button class="btn btn-danger btn-sm" onclick="deleteAnn(${a.ann_id})">🗑️</button>
      </div>
    </div>`).join(''):'<div class="empty-state"><div class="icon">📢</div><h3>No announcements yet</h3></div>';
}
async function postAnnouncement(){
  const body={title:document.getElementById('ann-title').value.trim(),body:document.getElementById('ann-body').value.trim(),priority:document.getElementById('ann-priority').value};
  if(!body.title||!body.body)return toast('Title and message required','error');
  const res=await fetch(`${API}/admin/announcements`,{method:'POST',headers:auth(),body:JSON.stringify(body)});
  const data=await res.json();
  toast(res.ok?data.message:data.error,res.ok?'success':'error');
  if(res.ok){closeModal('annModal');loadAnnouncements();}
}
async function deleteAnn(id){
  if(!confirm('Delete this announcement?'))return;
  const res=await fetch(`${API}/admin/announcements/${id}`,{method:'DELETE',headers:auth()});
  const data=await res.json();
  toast(res.ok?data.message:data.error,res.ok?'success':'error');
  if(res.ok)loadAnnouncements();
}

// ── ANOMALIES ────────────────────────────────────────
async function loadAnomalies(){
  const res=await fetch(`${API}/ai/anomalies`,{headers:auth()});
  const{anomalies}=await res.json();
  document.getElementById('anomalyList').innerHTML=anomalies.length?anomalies.map(a=>`
    <div class="anomaly-card anomaly-${a.severity}">
      <div class="anomaly-type" style="color:${a.severity==='CRITICAL'?'#b91c1c':a.severity==='HIGH'?'#ef4444':'#f59e0b'}">${a.severity==='CRITICAL'?'🚨':a.severity==='HIGH'?'⚠️':'⚡'} ${a.type} · ${a.severity}</div>
      <div class="anomaly-desc">${a.description}</div>
      <div style="font-size:.72rem;color:var(--text-muted);margin-top:.3rem">${a.detected_at}</div>
    </div>`).join(''):'<div class="empty-state"><div class="icon">✅</div><h3>No Anomalies Detected</h3><p>System is operating normally.</p></div>';
}

// ── AUDIT LOGS ────────────────────────────────────────
async function loadAuditLogs(){
  const res=await fetch(`${API}/admin/audit?limit=300`,{headers:auth()});
  allLogs=(await res.json()).logs||[];
  renderAudit(allLogs);
}
function renderAudit(logs){
  document.getElementById('auditTable').innerHTML=logs.map(l=>`
    <tr>
      <td>${l.log_id}</td>
      <td style="font-size:.78rem;max-width:120px;overflow:hidden;text-overflow:ellipsis">${l.user_id||'—'}</td>
      <td><span class="badge ${getBadge(l.action)}">${l.action}</span></td>
      <td style="font-size:.78rem;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${l.details||''}">${l.details||'—'}</td>
      <td style="font-size:.78rem;white-space:nowrap">${new Date(l.timestamp).toLocaleString()}</td>
      <td style="font-size:.78rem">${l.ip_address||'—'}</td>
    </tr>`).join('');
}
function getBadge(a){
  if(!a)return 'badge-secondary';
  if(a.includes('FAIL')||a.includes('DUPLICATE')||a.includes('DELETE'))return 'badge-danger';
  if(a.includes('LOGIN')||a.includes('GOOGLE'))return 'badge-primary';
  if(a.includes('VOTE'))return 'badge-success';
  if(a.includes('CREATE')||a.includes('ADD')||a.includes('POST'))return 'badge-warning';
  return 'badge-secondary';
}
function filterAudit(){
  const q=document.getElementById('auditSearch').value.toLowerCase();
  renderAudit(allLogs.filter(l=>(l.action||'').toLowerCase().includes(q)||(l.user_id||'').toLowerCase().includes(q)||(l.details||'').toLowerCase().includes(q)));
}
