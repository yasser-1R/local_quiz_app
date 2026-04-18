(function(){
  const root = document.getElementById('editor');
  const quizId = root.dataset.quizId ? parseInt(root.dataset.quizId, 10) : null;
  const existingRaw = root.dataset.existing;
  const existing = existingRaw ? JSON.parse(existingRaw) : null;

  const state = {
    title: existing ? existing.title : '',
    description: existing ? existing.description || '' : '',
    category: existing ? existing.category || '' : '',
    questions: existing
      ? existing.questions.map(q => ({
          question_text: q.question_text,
          time_limit_seconds: q.time_limit_seconds,
          correct_choice_index: q.correct_choice_index,
          explanation: q.explanation || '',
          choices: q.choices.map(c => c.choice_text),
        }))
      : [],
  };

  function render() {
    root.innerHTML = `
      <label>Titre</label>
      <input id="qz-title" value="${escapeAttr(state.title)}" />
      <label>Description</label>
      <input id="qz-desc" value="${escapeAttr(state.description)}" />
      <label>Categorie</label>
      <input id="qz-cat" value="${escapeAttr(state.category)}" />

      <div style="margin-top:16px; display:flex; justify-content:space-between; align-items:center;">
        <h3>Questions (${state.questions.length})</h3>
        <div style="display:flex; gap:8px;">
          <button class="btn" id="importJson">📥 Importer JSON</button>
          <button class="btn primary" id="addQ">+ Ajouter question</button>
        </div>
      </div>
      <input type="file" id="jsonFile" accept=".json" style="display:none;" />
      <div class="json-import-hint">Format JSON: { "title": "...", "questions": [{ "question_text": "...", "choices": ["a","b","c","d"], "correct_choice_index": 0, "time_limit_seconds": 20 }] }</div>
      <div id="qList"></div>

      <div style="margin-top:18px;">
        <button class="btn primary big" id="saveBtn">${quizId ? 'Enregistrer' : 'Creer le quiz'}</button>
        <a class="btn" href="/teacher">Annuler</a>
      </div>`;

    document.getElementById('qz-title').oninput = e => state.title = e.target.value;
    document.getElementById('qz-desc').oninput  = e => state.description = e.target.value;
    document.getElementById('qz-cat').oninput   = e => state.category = e.target.value;
    document.getElementById('addQ').onclick = () => {
      state.questions.push({
        question_text: '',
        time_limit_seconds: 20,
        correct_choice_index: 0,
        explanation: '',
        choices: ['', '', '', ''],
      });
      render();
    };
    document.getElementById('importJson').onclick = () => document.getElementById('jsonFile').click();
    document.getElementById('jsonFile').onchange = handleJsonImport;
    document.getElementById('saveBtn').onclick = save;

    const list = document.getElementById('qList');
    list.innerHTML = state.questions.map((q, i) => questionHtml(q, i)).join('');
    state.questions.forEach((q, i) => bindQuestion(q, i));
  }

  function questionHtml(q, i) {
    return `
      <div class="q-editor">
        <div class="row between"><b>Question ${i+1}</b>
          <div>
            <button class="btn" data-up="${i}">▲</button>
            <button class="btn" data-down="${i}">▼</button>
            <button class="btn danger" data-del="${i}">Supprimer</button>
          </div>
        </div>
        <label>Texte de la question</label>
        <textarea data-qtext="${i}" rows="2">${escapeText(q.question_text)}</textarea>

        <div class="choices">
          ${q.choices.map((c, ci) => `
            <div>
              <label class="inline">Reponse ${ci+1}</label>
              <input data-choice="${i}:${ci}" value="${escapeAttr(c)}" />
            </div>`).join('')}
        </div>

        <div class="row gap mt wrap">
          <label class="inline">Correcte:
            <select data-correct="${i}">
              ${[0,1,2,3].map(n => `
                <option value="${n}" ${q.correct_choice_index===n?'selected':''}>Reponse ${n+1}</option>
              `).join('')}
            </select>
          </label>
          <label class="inline">Temps (s):
            <input type="number" min="5" max="120" data-time="${i}" value="${q.time_limit_seconds}" style="width:80px;display:inline-block;" />
          </label>
        </div>

        <label>Explication (optionnel)</label>
        <input data-expl="${i}" value="${escapeAttr(q.explanation)}" />
      </div>`;
  }

  function bindQuestion(q, i) {
    document.querySelector(`[data-qtext="${i}"]`).oninput = e => q.question_text = e.target.value;
    q.choices.forEach((_, ci) => {
      document.querySelector(`[data-choice="${i}:${ci}"]`).oninput = e => q.choices[ci] = e.target.value;
    });
    document.querySelector(`[data-correct="${i}"]`).onchange = e => q.correct_choice_index = parseInt(e.target.value,10);
    document.querySelector(`[data-time="${i}"]`).oninput = e => q.time_limit_seconds = parseInt(e.target.value,10) || 20;
    document.querySelector(`[data-expl="${i}"]`).oninput = e => q.explanation = e.target.value;
    document.querySelector(`[data-del="${i}"]`).onclick = () => { state.questions.splice(i,1); render(); };
    document.querySelector(`[data-up="${i}"]`).onclick = () => {
      if (i === 0) return;
      [state.questions[i-1], state.questions[i]] = [state.questions[i], state.questions[i-1]];
      render();
    };
    document.querySelector(`[data-down="${i}"]`).onclick = () => {
      if (i === state.questions.length - 1) return;
      [state.questions[i+1], state.questions[i]] = [state.questions[i], state.questions[i+1]];
      render();
    };
  }

  async function save() {
    if (!state.title.trim()) { alert('Veuillez entrer un titre'); return; }
    if (!state.questions.length) { alert('Ajoutez au moins une question'); return; }
    for (const q of state.questions) {
      if (!q.question_text.trim()) { alert('Toutes les questions doivent avoir un texte'); return; }
      if (q.choices.some(c => !c.trim())) { alert('Remplissez les 4 choix'); return; }
    }
    const payload = {
      title: state.title, description: state.description, category: state.category,
      questions: state.questions.map(q => ({
        question_text: q.question_text,
        time_limit_seconds: q.time_limit_seconds,
        correct_choice_index: q.correct_choice_index,
        explanation: q.explanation,
        choices: q.choices,
      })),
    };
    const url = quizId ? `/api/quizzes/${quizId}` : '/api/quizzes';
    const method = quizId ? 'PUT' : 'POST';
    const res = await fetch(url, {
      method, headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    if (!res.ok) { alert('Erreur lors de la sauvegarde'); return; }
    window.location.href = '/teacher';
  }

  function escapeAttr(s){return (''+s).replace(/[&<>"']/g,c=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function escapeText(s){return (''+s).replace(/[&<>]/g,c=>({ '&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

  function handleJsonImport(e) {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function(event) {
      try {
        const data = JSON.parse(event.target.result);
        if (Array.isArray(data.questions)) {
          state.title = data.title || state.title;
          state.description = data.description || state.description;
          state.category = data.category || state.category;
          state.questions = data.questions.map(q => ({
            question_text: q.question_text || q.question || '',
            time_limit_seconds: q.time_limit_seconds || q.time_limit || q.time || 20,
            correct_choice_index: q.correct_choice_index || q.correct_answer || q.correct || 0,
            explanation: q.explanation || '',
            choices: q.choices || q.options || ['', '', '', ''],
          }));
          render();
          alert(`${state.questions.length} questions importees avec succes!`);
        } else if (Array.isArray(data)) {
          state.questions = data.map(q => ({
            question_text: q.question_text || q.question || '',
            time_limit_seconds: q.time_limit_seconds || q.time_limit || q.time || 20,
            correct_choice_index: q.correct_choice_index || q.correct_answer || q.correct || 0,
            explanation: q.explanation || '',
            choices: q.choices || q.options || ['', '', '', ''],
          }));
          render();
          alert(`${state.questions.length} questions importees avec succes!`);
        } else {
          alert('Format JSON invalide. Attendu: {questions: [...]} ou [...]');
        }
      } catch (err) {
        alert('Erreur lors de la lecture du fichier JSON: ' + err.message);
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  }

  render();
})();
