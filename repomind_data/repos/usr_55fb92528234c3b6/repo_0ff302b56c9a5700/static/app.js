const form=document.getElementById("studioForm"), loading=document.getElementById("loading"), errorBox=document.getElementById("error"), results=document.getElementById("results"), runBtn=document.getElementById("runBtn");
document.querySelectorAll('.drop-card input[type=file]').forEach(input=>input.addEventListener('change',()=>{const label=input.closest('.drop-card');label.querySelector('.picked').textContent=input.files[0]?.name||'';}));
form.addEventListener("submit",async e=>{
 e.preventDefault(); errorBox.classList.add("hidden");results.classList.add("hidden");loading.classList.remove("hidden");runBtn.disabled=true;
 try{
  const response=await fetch("/api/generate",{method:"POST",body:new FormData(form)});
  const data=await response.json();
  if(!response.ok)throw new Error(data.detail||"The request could not be completed.");
  render(data);
 }catch(err){errorBox.textContent=err.message;errorBox.classList.remove("hidden");}
 finally{loading.classList.add("hidden");runBtn.disabled=false;}
});
function esc(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function card(title,body,wide=false){return `<article class="output-card ${wide?'wide':''}"><h3>${title}</h3>${body}</article>`}
function render(d){
 document.getElementById("generationMessage").textContent=d.generation_message+" · "+d.generation_mode;
 document.getElementById("download").href=d.download_url;
 const board=d.workflow.agents.map(a=>`<div class="agent"><div class="agent-top"><b>${esc(a.name)}</b><span class="state ${a.state}">${esc(a.state)}</span></div><small>${esc(a.detail)}</small></div>`).join("");
 document.getElementById("agentBoard").innerHTML=board;
 const c=d.content;let html="";
 html+=card("Product description",`<p>${esc(c.product_description)}</p>`,true);
 html+=card("Key features",`<ul>${(c.key_features||[]).map(x=>`<li>${esc(x)}</li>`).join("")}</ul>`);
 html+=card("FAQs",(c.faqs||[]).map(x=>`<div class="faq"><b>${esc(x.question)}</b><p>${esc(x.answer)}</p></div>`).join(""));
 const ad=c.advertisement_copy||{};html+=card("Advertisement copy",`<p><b>${esc(ad.headline)}</b></p><p>${esc(ad.body)}</p><p><b>CTA:</b> ${esc(ad.call_to_action)}</p>`);
 const sm=c.social_media_content||{};html+=card("Social media content",`<p><b>Instagram</b><br>${esc(sm.instagram)}</p><p><b>LinkedIn</b><br>${esc(sm.linkedin)}</p><p><b>Short caption</b><br>${esc(sm.short_caption)}</p>`,true);
 const cc=c.content_consistency||{};html+=card("Consistency & claims review",`<p><b>${esc(cc.status)}</b></p><ul>${(cc.checks||[]).map(x=>`<li>${esc(x)}</li>`).join("")}${(cc.customer_concerns||[]).map(x=>`<li>Review concern: ${esc(x)}</li>`).join("")}</ul>`,true);
 const ins=d.input_status||{};html+=card("Input processing status",`<ul>${Object.entries(ins).map(([k,v])=>`<li><b>${esc(k.replaceAll("_"," "))}:</b> ${esc(v)}</li>`).join("")}</ul>`);
 document.getElementById("resultGrid").innerHTML=html;
 document.getElementById("disclaimer").textContent=d.disclaimer;
 results.classList.remove("hidden");results.scrollIntoView({behavior:"smooth",block:"start"});
}
