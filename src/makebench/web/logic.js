/* Makebench: blocos locais → modelo neutro. Nenhum comando do sistema nesta vista. */
'use strict';
let context = {components: [], functions: []};
let bridge, workspace, current = null, loading = false, timer = null, initialSnapshot = null, lastSnapshot = null;
const byId = id => context.components.find(c => c.id === id);
const options = kinds => () => {
  const rows = context.components.filter(c => !kinds || kinds.includes(c.kind)).map(c => [c.name, c.id]);
  return rows.length ? rows : [['Nenhum componente disponível', '@missing']];
};
const dropdown = kinds => new Blockly.FieldDropdown(options(kinds));
const textKinds = ['label', 'button', 'text_input', 'checkbox', 'output'];
const definitions = [
 {type:'mb_event', message0:'%1 %2 fazer %3', args0:[{type:'field_label_serializable',name:'TITLE',text:'Evento'},{type:'input_dummy'},{type:'input_statement',name:'DO'}],colour:30},
 {type:'mb_log',message0:'registrar na saída %1',args0:[{type:'input_value',name:'VALUE'}],previousStatement:null,nextStatement:null,colour:210},
 {type:'mb_message',message0:'mostrar mensagem %1',args0:[{type:'input_value',name:'VALUE'}],previousStatement:null,nextStatement:null,colour:210},
 {type:'mb_assign',message0:'definir variável %1 como %2',args0:[{type:'field_input',name:'NAME',text:'contador'},{type:'input_value',name:'VALUE'}],previousStatement:null,nextStatement:null,colour:330},
 {type:'mb_variable',message0:'valor de %1',args0:[{type:'field_input',name:'NAME',text:'contador'}],output:null,colour:330},
 {type:'mb_if',message0:'se %1 então %2 senão %3',args0:[{type:'input_value',name:'CONDITION'},{type:'input_statement',name:'THEN'},{type:'input_statement',name:'ELSE'}],previousStatement:null,nextStatement:null,colour:120},
 {type:'mb_repeat',message0:'repetir %1 vezes %2',args0:[{type:'input_value',name:'COUNT'},{type:'input_statement',name:'BODY'}],previousStatement:null,nextStatement:null,colour:120},
 {type:'mb_join',message0:'juntar %1 com %2',args0:[{type:'input_value',name:'LEFT'},{type:'input_value',name:'RIGHT'}],output:null,colour:160},
 {type:'mb_binary',message0:'%1 %2 %3',args0:[{type:'input_value',name:'LEFT'},{type:'field_dropdown',name:'OP',options:[['+','+'],['−','-'],['×','*'],['÷','/'],['=','=='],['≠','!='],['<','<'],['≤','<='],['>','>'],['≥','>='],['e','and'],['ou','or']]},{type:'input_value',name:'RIGHT'}],output:null,inputsInline:true,colour:230},
 {type:'mb_run',message0:'executar programa %1 argumentos %2 administrador %3',args0:[{type:'input_value',name:'PROGRAM'},{type:'input_value',name:'ARGUMENTS'},{type:'field_checkbox',name:'ADMIN',checked:false}],previousStatement:null,nextStatement:null,inputsInline:false,colour:20},
 {type:'mb_script',message0:'executar Bash %1 argumentos %2 administrador %3',args0:[{type:'input_value',name:'SOURCE'},{type:'input_value',name:'ARGUMENTS'},{type:'field_checkbox',name:'ADMIN',checked:false}],previousStatement:null,nextStatement:null,inputsInline:false,colour:20},
 {type:'mb_ask',message0:'perguntar %1 %2 opções %3 guardar em %4',args0:[{type:'field_dropdown',name:'KIND',options:[['texto','text'],['opção','choice'],['arquivo','file'],['pasta','directory']]},{type:'input_value',name:'PROMPT'},{type:'input_value',name:'OPTIONS'},{type:'field_input',name:'NAME',text:'resposta'}],previousStatement:null,nextStatement:null,inputsInline:false,colour:180},
 {type:'mb_confirm',message0:'confirmar para continuar %1',args0:[{type:'input_value',name:'PROMPT'}],previousStatement:null,nextStatement:null,inputsInline:false,colour:180},
 {type:'mb_call',message0:'chamar função %1 com %2',args0:[{type:'field_input',name:'FUNCTION',text:'saudacao'},{type:'input_value',name:'VALUE'}],previousStatement:null,nextStatement:null,colour:290},
];
const scopes=[['do projeto','project'],['desta janela','window'],['deste fluxo','local']];
for(const type of ['mb_assign','mb_variable','mb_ask']) {
 const definition=definitions.find(d=>d.type===type);
 definition.message0 += ' %'+(definition.args0.length+1);
 definition.args0.push({type:'field_dropdown',name:'SCOPE',options:scopes});
}
Blockly.defineBlocksWithJsonArray(definitions);
Blockly.Msg.DELETE_BLOCK='Remover bloco';Blockly.Msg.DELETE_X_BLOCKS='Remover %1 blocos';
Blockly.Msg.COLLAPSE_BLOCK='Recolher bloco';Blockly.Msg.COLLAPSE_ALL='Recolher todos';
Blockly.Msg.EXPAND_BLOCK='Expandir bloco';Blockly.Msg.EXPAND_ALL='Expandir todos';
for(const [type,label,field] of [['go_state','ir para estado','STATE'],['open_window','abrir janela','WINDOW'],['close_window','fechar esta janela',null]]) {
 Blockly.Blocks['mb_'+type]={init(){
   const input=this.appendDummyInput().appendField(label);
   if(field) input.appendField(new Blockly.FieldDropdown(()=>{
     const values=field==='WINDOW'?(context.windows||[]):(context.states||[]);
     return values.length?values.map(item=>[item.name,item.id]):[['Padrão','@default']];
   }),field);
   if(type==='open_window')this.appendDummyInput().appendField('fechar esta').appendField(new Blockly.FieldCheckbox('FALSE'),'CLOSE');
   this.setPreviousStatement(true);this.setNextStatement(true);this.setColour(210);
 }};
}
for (const [type, label, kinds] of [
 ['set_text','alterar texto de',textKinds],['set_enabled','habilitar componente',null],
 ['set_value','alterar progresso de',['progress']],['show_page','mostrar página',['page']],
 ['read_text','texto de',textKinds],['read_checked','seleção de',['checkbox']],['read_value','progresso de',['progress']]
]) {
 Blockly.Blocks['mb_' + type] = {init() {
   this.appendDummyInput().appendField(label).appendField(dropdown(kinds),'COMPONENT');
   if (type.startsWith('read_')) this.setOutput(true);
   else { if(type !== 'show_page') this.appendValueInput('VALUE').appendField('para'); this.setPreviousStatement(true); this.setNextStatement(true); }
   this.setColour(210);
 }};
}
Blockly.Blocks.mb_multiline = {
 init(){this.text_='';this.appendDummyInput().appendField(new Blockly.FieldLabelSerializable('Texto / script'),'SUMMARY');this.setOutput(true);this.setColour(160);this.setTooltip('Use Editar texto ou script para alterar várias linhas.');},
 saveExtraState(){return {text:this.text_};},
 loadExtraState(state){this.text_=String(state.text || '');this.setFieldValue(this.text_.split('\n')[0].slice(0,60) || 'Texto / script','SUMMARY');}
};
const block = (type, inputs) => ({kind:'block', type, ...(inputs ? {inputs} : {})});
const value = (type, fields) => ({shadow:{type,fields}});
const emptyList=()=>({block:{type:'lists_create_with',extraState:{itemCount:0}}});
const toolbox = {kind:'categoryToolbox',contents:[
 {kind:'category',name:'Interface',colour:210,contents:[block('mb_set_text',{VALUE:value('text',{TEXT:'Novo texto'})}),block('mb_set_enabled',{VALUE:value('logic_boolean',{BOOL:'TRUE'})}),block('mb_set_value',{VALUE:value('math_number',{NUM:50})}),block('mb_show_page'),block('mb_go_state'),block('mb_open_window'),block('mb_close_window'),block('mb_message',{VALUE:value('text',{TEXT:'Olá!'})}),block('mb_log',{VALUE:value('text',{TEXT:'Tudo pronto'})}),block('mb_read_text'),block('mb_read_checked'),block('mb_read_value')]},
 {kind:'category',name:'Condições e repetição',colour:120,contents:[block('mb_if',{CONDITION:value('logic_boolean',{BOOL:'TRUE'})}),block('mb_repeat',{COUNT:value('math_number',{NUM:3})}),block('mb_binary',{LEFT:value('math_number',{NUM:0}),RIGHT:value('math_number',{NUM:0})})]},
 {kind:'category',name:'Valores e variáveis',colour:330,contents:[block('text'),block('math_number'),block('logic_boolean'),block('mb_join',{LEFT:value('text',{TEXT:'Olá, '}),RIGHT:value('text',{TEXT:'Linux'})}),block('mb_assign',{VALUE:value('math_number',{NUM:0})}),block('mb_variable')]},
 {kind:'category',name:'Perguntas',colour:180,contents:[block('mb_ask',{PROMPT:value('text',{TEXT:'Qual é o seu nome?'}),OPTIONS:emptyList()}),block('mb_confirm',{PROMPT:value('text',{TEXT:'Deseja continuar?'})})]},
 {kind:'category',name:'Programas e scripts',colour:20,contents:[block('mb_run',{PROGRAM:value('text',{TEXT:'uname'}),ARGUMENTS:emptyList()}),block('mb_script',{SOURCE:value('text',{TEXT:'printf "Olá, %s\\n" "$1"'}),ARGUMENTS:emptyList()}),{kind:'block',type:'lists_create_with',extraState:{itemCount:0}}]},
 {kind:'category',name:'Funções próprias',colour:290,contents:[block('mb_call',{VALUE:value('text',{TEXT:'Linux'})})]}
]};

function compileWorkspace() {
 const errors = [];
 const hats = workspace.getTopBlocks(false).filter(b => b.type === 'mb_event');
 const hat = hats[0];
 if(hats.length !== 1) errors.push('Mantenha um único evento neste fluxo.');
 if(workspace.getTopBlocks(false).some(b => b !== hat && !b.isInsertionMarker())) errors.push('Há blocos soltos. Conecte-os ao evento ou remova-os.');
 function base(b, op) { const n={id:b.id,op}; const comment=b.getCommentText(); if(comment) n.comment=comment; return n; }
 function expr(b) {
   if(!b) throw Error('Falta preencher uma entrada de valor.');
   if(!b.isEnabled()) throw Error('Há um valor desativado. Ative-o para gerar código.');
   const n = base(b, 'literal');
   if(b.type==='mb_multiline') n.value=b.text_;
   else if(b.type === 'text') n.value=b.getFieldValue('TEXT');
   else if(b.type === 'math_number') n.value=Number(b.getFieldValue('NUM'));
   else if(b.type === 'logic_boolean') n.value=b.getFieldValue('BOOL')==='TRUE';
   else if(b.type==='lists_create_with') {n.op='list';n.items=[];for(let index=0;b.getInput('ADD'+index);index++)n.items.push(expr(b.getInputTargetBlock('ADD'+index)));}
   else if(b.type==='mb_variable') {n.op='variable'; n.name=b.getFieldValue('NAME');n.scope=b.getFieldValue('SCOPE')||'project';if(n.scope==='project')delete n.scope;}
   else if(b.type.startsWith('mb_read_')) {n.op='read'; n.attribute=b.type.slice(8); n.component=b.getFieldValue('COMPONENT');}
   else if(['mb_binary','mb_join'].includes(b.type)) {n.op=b.type.slice(3);n.left=expr(b.getInputTargetBlock('LEFT'));n.right=expr(b.getInputTargetBlock('RIGHT'));if(n.op==='binary')n.operator=b.getFieldValue('OP');}
   else throw Error('Bloco de valor desconhecido: ' + b.type);
   return n;
 }
 function chain(first) {
   const items=[]; let b=first;
   while(b) {
     if(!b.isEnabled()) throw Error('Bloco desativado: ative-o ou remova-o para gerar código.');
     const op=b.type.slice(3), n=base(b,op);
     if(['log','message','set_text','set_enabled','set_value','assign','call'].includes(op)) n.value=expr(b.getInputTargetBlock('VALUE'));
     if(['set_text','set_enabled','set_value','show_page'].includes(op)) n.component=b.getFieldValue('COMPONENT');
     if(op==='assign') {n.name=b.getFieldValue('NAME');n.scope=b.getFieldValue('SCOPE')||'project';if(n.scope==='project')delete n.scope;}
     else if(op==='go_state')n.state=b.getFieldValue('STATE');
     else if(op==='open_window'){n.window=b.getFieldValue('WINDOW');n.close_current=b.getFieldValue('CLOSE')==='TRUE';}
     else if(op==='call') n.function=b.getFieldValue('FUNCTION');
     else if(op==='run' || op==='script') {n[op==='run'?'program':'source']=expr(b.getInputTargetBlock(op==='run'?'PROGRAM':'SOURCE'));n.arguments=expr(b.getInputTargetBlock('ARGUMENTS'));n.admin=b.getFieldValue('ADMIN')==='TRUE';}
     else if(op==='ask') {n.kind=b.getFieldValue('KIND');n.name=b.getFieldValue('NAME');n.scope=b.getFieldValue('SCOPE')||'project';if(n.scope==='project')delete n.scope;n.prompt=expr(b.getInputTargetBlock('PROMPT'));n.options=expr(b.getInputTargetBlock('OPTIONS'));}
     else if(op==='confirm') n.prompt=expr(b.getInputTargetBlock('PROMPT'));
     else if(op==='if') {n.condition=expr(b.getInputTargetBlock('CONDITION'));n.then=chain(b.getInputTargetBlock('THEN'));n.else=chain(b.getInputTargetBlock('ELSE'));}
     else if(op==='repeat') {n.count=expr(b.getInputTargetBlock('COUNT'));n.body=chain(b.getInputTargetBlock('BODY'));}
     else if(!['log','message','set_text','set_enabled','set_value','show_page','assign','go_state','open_window','close_window'].includes(op)) throw Error('Operação desconhecida: ' + b.type);
     items.push(n); b=b.getNextBlock();
   }
   return items;
 }
 let body=null;
 try { if(hat) body=chain(hat.getInputTargetBlock('DO')); } catch(e) { errors.push(e.message); }
 return {body: errors.length ? null : body, errors};
}
function stateFor(node) {
 let type='mb_'+node.op, fields={}, inputs={};
 if(node.op==='literal') {
   if(typeof node.value==='string') {type='text';fields.TEXT=node.value;}
   else if(typeof node.value==='boolean') {type='logic_boolean';fields.BOOL=node.value?'TRUE':'FALSE';}
   else {type='math_number';fields.NUM=node.value;}
 }
 if(node.op==='list') {type='lists_create_with';node.items.forEach((item,index)=>inputs['ADD'+index]={block:stateFor(item)});}
 if(node.op==='run' || node.op==='script') fields.ADMIN=node.admin?'TRUE':'FALSE';
 if(node.op==='ask') fields.KIND=node.kind;
 if(node.component) fields.COMPONENT=node.component;
 if(node.name) fields.NAME=node.name;
 if(['variable','assign','ask'].includes(node.op))fields.SCOPE=node.scope||'project';
 if(node.op==='go_state')fields.STATE=node.state;
 if(node.op==='open_window'){fields.WINDOW=node.window;fields.CLOSE=node.close_current?'TRUE':'FALSE';}
 if(node.function) fields.FUNCTION=node.function;
 if(node.operator) fields.OP=node.operator;
 if(node.op==='read') type='mb_read_'+node.attribute;
 for(const [key,name] of [['value','VALUE'],['left','LEFT'],['right','RIGHT'],['condition','CONDITION'],['count','COUNT'],['program','PROGRAM'],['source','SOURCE'],['arguments','ARGUMENTS'],['prompt','PROMPT'],['options','OPTIONS']]) if(node[key] && typeof node[key]==='object') inputs[name]={block:stateFor(node[key])};
 for(const [key,name] of [['then','THEN'],['else','ELSE'],['body','BODY']]) if(node[key]?.length) inputs[name]={block:chainState(node[key])};
 const state={type,id:node.id,fields,inputs};
 if(node.op==='literal' && typeof node.value==='string' && node.value.includes('\n')){state.type='mb_multiline';state.fields={};state.extraState={text:node.value};}
 if(node.op==='list')state.extraState={itemCount:node.items.length};
 if(node.comment) state.icons={comment:{text:node.comment}};
 return state;
}
function chainState(nodes) { const first=stateFor(nodes[0]); let tail=first; for(const node of nodes.slice(1)){tail.next={block:stateFor(node)};tail=tail.next.block;} return first; }
function rebuild(flow) {
 workspace.clear();
 const state={type:'mb_event',id:'event_'+flow.id,x:40,y:40,fields:{TITLE:flow.name},inputs:{}};
 if(flow.body?.length) state.inputs.DO={block:chainState(flow.body)};
 Blockly.serialization.workspaces.load({blocks:{languageVersion:0,blocks:[state]},workspaceComments:flow.workspace?.workspaceComments || []},workspace);
}
function canonical(value) {
 if(Array.isArray(value)) return '['+value.map(canonical).join(',')+']';
 if(value && typeof value==='object') return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
 return JSON.stringify(value);
}
function setDocument(payload) {
 clearTimeout(timer);loading=true;Blockly.Events.disable();
 try {
 context=payload;
 current=payload.flow ? {flow:payload.flow,token:payload.token} : null;
 workspace.clear();
 if(current) {
   const flow=current.flow;
   try {
     if(flow.workspace?.blocks) Blockly.serialization.workspaces.load(flow.workspace,workspace);
     else rebuild(flow);
     // O modelo neutro é a autoridade. A vista salva só é usada quando corresponde.
     if(flow.body!==null && canonical(compileWorkspace().body)!==canonical(flow.body)) rebuild(flow);
   } catch(e) { if(flow.body===null){bridge.problem('Não foi possível recuperar o rascunho: '+e.message);current=null;} else rebuild(flow); }
   if(current) {
     const hat=workspace.getAllBlocks(false).find(b=>b.type==='mb_event');
     if(hat){hat.setFieldValue(flow.name,'TITLE');hat.setDeletable(false);hat.setMovable(false);hat.setEditable(false);}
   }
 }
 document.getElementById('empty').style.display=current?'none':'flex';
 workspace.getAllBlocks(false).forEach(block=>{
   if(block.type==='mb_call')block.setTooltip(()=>{
     const name=block.getFieldValue('FUNCTION');const info=(context.function_info||[]).find(item=>item.name===name);
     return info?info.signature+'\n'+info.description:'Função ausente no arquivo próprio. Abra Código para defini-la.';
   });
   if(['mb_run','mb_script'].includes(block.type))block.setTooltip(()=>block.getFieldValue('ADMIN')==='TRUE'?'Pede autorização pelo diálogo do sistema. O Makebench não recebe senhas.':'Executa programa do sistema, com argumentos separados.');
 });
 workspace.clearUndo();
 } finally {Blockly.Events.enable();loading=false;}
 initialSnapshot=canonical({compiled:compileWorkspace(),workspace:Blockly.serialization.workspaces.save(workspace)});lastSnapshot=initialSnapshot;
}
function flush(force=false) {
 clearTimeout(timer);
 if(!current || loading) return null;
 const compiled=compileWorkspace();
 const state=Blockly.serialization.workspaces.save(workspace);
 const snapshot=canonical({compiled,workspace:state});
 if(!force && snapshot===lastSnapshot) return null;
 lastSnapshot=snapshot;
 if(snapshot===initialSnapshot) return {token:current.token,flow:current.flow.id,body:current.flow.body,errors:current.flow.errors || [],workspace:current.flow.workspace || {}};
 return {token:current.token,flow:current.flow.id,...compiled,workspace:state};
}
function report() {const result=flush();if(result) bridge.changed(JSON.stringify(result));}
function textValue(id) {
 let b=workspace.getBlockById(id);
 if(b?.type==='mb_script')b=b.getInputTargetBlock('SOURCE');
 if(!b || !['text','mb_multiline'].includes(b.type))return null;
 return {id:b.id,text:b.type==='text'?b.getFieldValue('TEXT'):b.text_};
}
function setTextValue(id,text) {
 const previous=workspace.getBlockById(id);
 if(!previous || !['text','mb_multiline'].includes(previous.type))return false;
 Blockly.Events.disable();
 try {
   let b=previous;
   if(b.type==='text'){
     const target=b.outputConnection.targetConnection,position=b.getRelativeToSurfaceXY(),comment=b.getCommentText(),shadow=b.isShadow();
     b.dispose(false);b=workspace.newBlock('mb_multiline',id);b.setShadow(shadow);b.initSvg();
     if(target)b.outputConnection.connect(target);else b.moveBy(position.x,position.y);
     if(comment)b.setCommentText(comment);
   }
   b.text_=text;b.setFieldValue(text.split('\n')[0].slice(0,60) || 'Texto / script','SUMMARY');b.render();
 } finally {Blockly.Events.enable();}
 bridge.pending(current.token);report();return true;
}
window.makebench={setDocument,flush,compileWorkspace,textValue,setTextValue, get workspace(){return workspace;}};
new QWebChannel(qt.webChannelTransport, channel => {
 bridge=channel.objects.bridge;
 // Blockly 13 disponibiliza um serializador explícito para comentários soltos.
 try {Blockly.serialization.registry.register('workspaceComments',new Blockly.serialization.workspaceComments.WorkspaceCommentSerializer());} catch(e) { /* Já registrado nesta versão. */ }
 workspace=Blockly.inject('workspace',{toolbox,renderer:'zelos',media:'vendor/blockly/media/',sounds:false,trashcan:true,comments:true,collapse:true,disable:false,maxBlocks:5000,maxUndo:0,zoom:{controls:true,wheel:true,startScale:0.85},grid:{spacing:24,length:2,colour:'var(--mb-grid)',snap:false}});
 workspace.addChangeListener(event => {
   if(loading) return;
   if(event.type===Blockly.Events.SELECTED && current) bridge.selected(current.flow.id,event.newElementId || '');
   if(!event.isUiEvent && current) {bridge.pending(current.token);clearTimeout(timer);timer=setTimeout(report,220);}
 });
 bridge.documentChanged.connect(json => {try{setDocument(JSON.parse(json));}catch(e){bridge.problem(e.message);}});
 window.addEventListener('keydown', event => {
   if(event.code==='Space' && !event.ctrlKey && !event.altKey && !['INPUT','TEXTAREA'].includes(event.target.tagName) && !event.target.isContentEditable){event.preventDefault();bridge.command('find_block');return;}
   if(!(event.ctrlKey || event.metaKey) || event.altKey) return;
   const key=event.key.toLowerCase();
   const command=key==='s' && !event.shiftKey?'save':key==='z'?(event.shiftKey?'redo':'undo'):key==='y'?'redo':null;
   if(command){event.preventDefault();event.stopImmediatePropagation();bridge.command(command);}
 },true);
 bridge.ready();
});

window.makebench.applyTheme=function(t){
 document.documentElement.style.setProperty('--mb-canvas',t.canvas);document.documentElement.style.setProperty('--mb-text',t.text);document.documentElement.style.setProperty('--mb-grid',t.border);
 const theme=Blockly.Theme.defineTheme('makebench',{base:Blockly.Themes.Classic,
   componentStyles:{workspaceBackgroundColour:t.canvas,toolboxBackgroundColour:t.panel,
     toolboxForegroundColour:t.text,flyoutBackgroundColour:t.raised,flyoutForegroundColour:t.text,
     flyoutOpacity:1,scrollbarColour:t.control,insertionMarkerColour:t.accent,insertionMarkerOpacity:.5,
     cursorColour:t.accent}});
 workspace.setTheme(theme);document.body.style.background=t.canvas;
};
window.makebench.addBlock=function(type){
 if(!current||!Blockly.Blocks[type])return false;
 const block=workspace.newBlock(type);block.initSvg();block.render();block.moveBy(80,180);block.select();return true;
};

window.makebench.selectedFunction=function(){const block=Blockly.getSelected();return block?.type==='mb_call'?block.getFieldValue('FUNCTION'):null;};
Blockly.ContextMenuRegistry.registry.register({id:'makebench_python',scopeType:Blockly.ContextMenuRegistry.ScopeType.BLOCK,
 displayText:'Ir ao Python',weight:50,preconditionFn:()=>'enabled',callback:()=>bridge.command('python')});
Blockly.ContextMenuRegistry.registry.register({id:'makebench_function',scopeType:Blockly.ContextMenuRegistry.ScopeType.BLOCK,
 displayText:'Abrir função',weight:51,preconditionFn:scope=>scope.block.type==='mb_call'?'enabled':'hidden',callback:()=>bridge.command('function')});

for(const type of ['mb_assign','mb_variable','mb_ask']) {
 const original=Blockly.Blocks[type].init;
 Blockly.Blocks[type].init=function(){
   original.call(this);
   const picker=new Blockly.FieldDropdown(()=>{
     const groups={project:'Do projeto',window:'Desta janela',local:'Deste fluxo'};
     const values=[['Escolher variável…','@none']];
     for(const scope of ['project','window','local'])for(const variable of context.variables||[]){
       if((variable.scope||'project')===scope)values.push([groups[scope]+' · '+variable.name,JSON.stringify({name:variable.name,scope})]);
     }
     return values;
   },function(value){
     if(value!=='@none'){
       const variable=JSON.parse(value);const block=this.getSourceBlock();
       if(block){block.setFieldValue(variable.name,'NAME');block.setFieldValue(variable.scope,'SCOPE');}
     }
     return value;
   });
   this.appendDummyInput('VARIABLE_PICKER').appendField(picker,'VARIABLE_PICKER');
 };
}
