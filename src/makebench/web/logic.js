/* Makebench: local blocks → neutral model. No system command in this view. */
'use strict';
// Interface language comes from the HTML entry (lang attribute); English is the source.
const PT_BR = {"No component available": "Nenhum componente disponível", "%1 %2 do %3": "%1 %2 fazer %3", "Event": "Evento", "write to output %1": "registrar na saída %1", "show message %1": "mostrar mensagem %1", "set variable %1 to %2": "definir variável %1 como %2", "counter": "contador", "value of %1": "valor de %1", "if %1 then %2 else %3": "se %1 então %2 senão %3", "repeat %1 times %2": "repetir %1 vezes %2", "join %1 with %2": "juntar %1 com %2", "and": "e", "or": "ou", "run program %1 arguments %2 administrator %3": "executar programa %1 argumentos %2 administrador %3", "run Bash %1 arguments %2 administrator %3": "executar Bash %1 argumentos %2 administrador %3", "ask %1 %2 options %3 store in %4": "perguntar %1 %2 opções %3 guardar em %4", "text": "texto", "choice": "opção", "file": "arquivo", "folder": "pasta", "answer": "resposta", "confirm to continue %1": "confirmar para continuar %1", "call function %1 with %2": "chamar função %1 com %2", "greet": "saudacao", "start terminal": "iniciar terminal", "send to terminal": "enviar ao terminal", "stop terminal": "encerrar terminal", "program (empty = shell)": "programa (vazio = shell)", "arguments": "argumentos", "input": "entrada", "project-wide": "do projeto", "this window": "desta janela", "this flow": "deste fluxo", "Delete block": "Remover bloco", "Delete %1 blocks": "Remover %1 blocos", "Collapse block": "Recolher bloco", "Collapse all": "Recolher todos", "Expand block": "Expandir bloco", "Expand all": "Expandir todos", "go to state": "ir para estado", "open window": "abrir janela", "close this window": "fechar esta janela", "Default": "Padrão", "close this one": "fechar esta", "change text of": "alterar texto de", "enable component": "habilitar componente", "change value of": "alterar valor de", "show page": "mostrar página", "text of": "texto de", "selection of": "seleção de", "value of": "valor de", "to": "para", "Text / script": "Texto / script", "Use Edit text or script to change several lines.": "Use Editar texto ou script para alterar várias linhas.", "Interface and navigation": "Interface e navegação", "New text": "Novo texto", "Hello!": "Olá!", "Variables and data": "Variáveis e dados", "Conditions": "Condições", "Loops": "Repetições", "Operations": "Operações", "Text": "Texto", "Hello, ": "Olá, ", "Events": "Eventos", "The current event sits at the top of the flow.": "O evento atual fica no topo do fluxo.", "Connect another event…": "Conectar outro evento…", "Tasks": "Tarefas", "printf \"Hello, Linux\\n\"": "printf \"Olá, Linux\\n\"", "All set": "Tudo pronto", "What is your name?": "Qual é o seu nome?", "Do you want to continue?": "Deseja continuar?", "Your functions": "Funções próprias", "Keep a single event in this flow.": "Mantenha um único evento neste fluxo.", "There are loose blocks. Connect them to the event or remove them.": "Há blocos soltos. Conecte-os ao evento ou remova-os.", "A value input is missing.": "Falta preencher uma entrada de valor.", "There is a disabled value. Enable it to generate code.": "Há um valor desativado. Ative-o para gerar código.", "Unknown value block: ": "Bloco de valor desconhecido: ", "Disabled block: enable or remove it to generate code.": "Bloco desativado: ative-o ou remova-o para gerar código.", "Unknown operation: ": "Operação desconhecida: ", "Could not recover the draft: ": "Não foi possível recuperar o rascunho: ", "Function missing from your file. Open Code to define it.": "Função ausente no arquivo próprio. Abra Código para defini-la.", "Asks for authorization through the system dialog. Makebench never receives passwords.": "Pede autorização pelo diálogo do sistema. O Makebench não recebe senhas.", "Runs a system program, with separate arguments.": "Executa programa do sistema, com argumentos separados.", "Go to Python": "Ir ao Python", "Open function": "Abrir função", "Project-wide": "Do projeto", "This window": "Desta janela", "This flow": "Deste fluxo", "Choose variable…": "Escolher variável…", "Toggle breakpoint": "Alternar ponto de parada", "Breakpoint": "Ponto de parada", "Function": "Função", "call %1": "chamar %1", "result of %1": "resultado de %1", "return %1": "retornar %1", "No function yet": "Nenhuma função ainda", "New function…": "Nova função…", "Choose a function to call.": "Escolha uma função para chamar.", "Keep a single function header here.": "Mantenha um único cabeçalho de função aqui.", "“Return” only works inside a function.": "“Retornar” só funciona dentro de uma função.", "Inputs are local variables of the function.": "As entradas são variáveis locais da função."};
const T = text => (document.documentElement.lang === 'pt-BR' && PT_BR[text]) || text;
let context = {components: [], functions: []};
let bridge, workspace, current = null, loading = false, timer = null, initialSnapshot = null, lastSnapshot = null;
const byId = id => context.components.find(c => c.id === id);
const options = kinds => () => {
  const rows = context.components.filter(c => !kinds || kinds.includes(c.kind)).map(c => [c.name, c.id]);
  return rows.length ? rows : [[T('No component available'), '@missing']];
};
const dropdown = kinds => new Blockly.FieldDropdown(options(kinds));
const textKinds = ['label', 'button', 'text_input', 'checkbox', 'output'];
const valueKinds = ['progress', 'number', 'slider'];
const definitions = [
 {type:'mb_event', message0:T('%1 %2 do %3'), args0:[{type:'field_label_serializable',name:'TITLE',text:T('Event')},{type:'input_dummy'},{type:'input_statement',name:'DO'}],colour:30},
 {type:'mb_log',message0:T('write to output %1'),args0:[{type:'input_value',name:'VALUE'}],previousStatement:null,nextStatement:null,colour:210},
 {type:'mb_message',message0:T('show message %1'),args0:[{type:'input_value',name:'VALUE'}],previousStatement:null,nextStatement:null,colour:210},
 {type:'mb_assign',message0:T('set variable %1 to %2'),args0:[{type:'field_input',name:'NAME',text:T('counter')},{type:'input_value',name:'VALUE'}],previousStatement:null,nextStatement:null,colour:330},
 {type:'mb_variable',message0:T('value of %1'),args0:[{type:'field_input',name:'NAME',text:T('counter')}],output:null,colour:330},
 {type:'mb_if',message0:T('if %1 then %2 else %3'),args0:[{type:'input_value',name:'CONDITION'},{type:'input_statement',name:'THEN'},{type:'input_statement',name:'ELSE'}],previousStatement:null,nextStatement:null,colour:120},
 {type:'mb_repeat',message0:T('repeat %1 times %2'),args0:[{type:'input_value',name:'COUNT'},{type:'input_statement',name:'BODY'}],previousStatement:null,nextStatement:null,colour:120},
 {type:'mb_join',message0:T('join %1 with %2'),args0:[{type:'input_value',name:'LEFT'},{type:'input_value',name:'RIGHT'}],output:null,colour:160},
 {type:'mb_binary',message0:'%1 %2 %3',args0:[{type:'input_value',name:'LEFT'},{type:'field_dropdown',name:'OP',options:[['+','+'],['−','-'],['×','*'],['÷','/'],['=','=='],['≠','!='],['<','<'],['≤','<='],['>','>'],['≥','>='],[T('and'),'and'],[T('or'),'or']]},{type:'input_value',name:'RIGHT'}],output:null,inputsInline:true,colour:230},
 {type:'mb_run',message0:T('run program %1 arguments %2 administrator %3'),args0:[{type:'input_value',name:'PROGRAM'},{type:'input_value',name:'ARGUMENTS'},{type:'field_checkbox',name:'ADMIN',checked:false}],previousStatement:null,nextStatement:null,inputsInline:false,colour:20},
 {type:'mb_script',message0:T('run Bash %1 arguments %2 administrator %3'),args0:[{type:'input_value',name:'SOURCE'},{type:'input_value',name:'ARGUMENTS'},{type:'field_checkbox',name:'ADMIN',checked:false}],previousStatement:null,nextStatement:null,inputsInline:false,colour:20},
 {type:'mb_ask',message0:T('ask %1 %2 options %3 store in %4'),args0:[{type:'field_dropdown',name:'KIND',options:[[T('text'),'text'],[T('choice'),'choice'],[T('file'),'file'],[T('folder'),'directory']]},{type:'input_value',name:'PROMPT'},{type:'input_value',name:'OPTIONS'},{type:'field_input',name:'NAME',text:T('answer')}],previousStatement:null,nextStatement:null,inputsInline:false,colour:180},
 {type:'mb_confirm',message0:T('confirm to continue %1'),args0:[{type:'input_value',name:'PROMPT'}],previousStatement:null,nextStatement:null,inputsInline:false,colour:180},
 {type:'mb_function', message0:T('%1 %2 do %3'), args0:[{type:'field_label_serializable',name:'TITLE',text:T('Function')},{type:'input_dummy'},{type:'input_statement',name:'DO'}],colour:290,tooltip:T('Inputs are local variables of the function.')},
 {type:'mb_return',message0:T('return %1'),args0:[{type:'input_value',name:'VALUE'}],previousStatement:null,colour:290},
 {type:'mb_call',message0:T('call function %1 with %2'),args0:[{type:'field_input',name:'FUNCTION',text:T('greet')},{type:'input_value',name:'VALUE'}],previousStatement:null,nextStatement:null,colour:290},
];
for(const type of ['terminal_start','terminal_send','terminal_stop']) {
 Blockly.Blocks['mb_'+type]={init(){
   this.appendDummyInput().appendField({terminal_start:T('start terminal'),terminal_send:T('send to terminal'),terminal_stop:T('stop terminal')}[type]).appendField(dropdown(['terminal']),'COMPONENT');
   if(type==='terminal_start'){this.appendValueInput('PROGRAM').appendField(T('program (empty = shell)'));this.appendValueInput('ARGUMENTS').appendField(T('arguments'));}
   if(type==='terminal_send')this.appendValueInput('VALUE').appendField(T('input'));
   this.setPreviousStatement(true);this.setNextStatement(true);this.setColour(20);
 }};
}
const functionOptions=()=>{
 const rows=(context.block_functions||[]).map(f=>[f.name+'('+f.params.join(', ')+')',f.id]);
 return rows.length?rows:[[T('No function yet'),'@missing']];
};
for(const [type,label,output] of [['mb_call_function','call %1',false],['mb_call_value','result of %1',true]]) {
 Blockly.Blocks[type]={init(){
   this.argCount_=0;
   const parts=T(label).split('%1');
   this.appendDummyInput('HEAD').appendField(parts[0].trim()).appendField(new Blockly.FieldDropdown(functionOptions,function(id){this.getSourceBlock()?.updateArgs_(id);return id;}),'FUNCTION');
   this.setInputsInline(true);this.setColour(290);
   if(output)this.setOutput(true);else{this.setPreviousStatement(true);this.setNextStatement(true);}
   this.updateArgs_(this.getFieldValue('FUNCTION'));
 },
 // One value input per function input; labels follow the current names.
 updateArgs_(id){
   const fn=(context.block_functions||[]).find(f=>f.id===id);
   const params=fn?fn.params:[];
   for(let i=params.length;this.getInput('ARG'+i);i++)this.removeInput('ARG'+i);
   params.forEach((name,i)=>{
     const input=this.getInput('ARG'+i)||this.appendValueInput('ARG'+i).appendField('','LABEL'+i);
     input.fieldRow.find(f=>f.name==='LABEL'+i)?.setValue(name);
   });
   this.argCount_=params.length;
 },
 saveExtraState(){return {count:this.argCount_};},
 loadExtraState(state){
   const count=state.count||0;
   for(let i=count;this.getInput('ARG'+i);i++)this.removeInput('ARG'+i);
   for(let i=0;i<count;i++)if(!this.getInput('ARG'+i))this.appendValueInput('ARG'+i).appendField('','LABEL'+i);
   this.argCount_=count;
 }
 };
}
const scopes=[[T('project-wide'),'project'],[T('this window'),'window'],[T('this flow'),'local']];
for(const type of ['mb_assign','mb_variable','mb_ask']) {
 const definition=definitions.find(d=>d.type===type);
 definition.message0 += ' %'+(definition.args0.length+1);
 definition.args0.push({type:'field_dropdown',name:'SCOPE',options:scopes});
}
Blockly.defineBlocksWithJsonArray(definitions);
Blockly.Msg.DELETE_BLOCK=T('Delete block');Blockly.Msg.DELETE_X_BLOCKS=T('Delete %1 blocks');
Blockly.Msg.COLLAPSE_BLOCK=T('Collapse block');Blockly.Msg.COLLAPSE_ALL=T('Collapse all');
Blockly.Msg.EXPAND_BLOCK=T('Expand block');Blockly.Msg.EXPAND_ALL=T('Expand all');
for(const [type,label,field] of [['go_state',T('go to state'),'STATE'],['open_window',T('open window'),'WINDOW'],['close_window',T('close this window'),null]]) {
 Blockly.Blocks['mb_'+type]={init(){
   const input=this.appendDummyInput().appendField(label);
   if(field) input.appendField(new Blockly.FieldDropdown(()=>{
     const values=field==='WINDOW'?(context.windows||[]):(context.states||[]);
     return values.length?values.map(item=>[item.name,item.id]):[[T('Default'),'@default']];
   }),field);
   if(type==='open_window')this.appendDummyInput().appendField(T('close this one')).appendField(new Blockly.FieldCheckbox('FALSE'),'CLOSE');
   this.setPreviousStatement(true);this.setNextStatement(true);this.setColour(210);
 }};
}
for (const [type, label, kinds] of [
 ['set_text',T('change text of'),textKinds],['set_enabled',T('enable component'),null],
 ['set_value',T('change value of'),valueKinds],['show_page',T('show page'),['page']],
 ['read_text',T('text of'),textKinds],['read_checked',T('selection of'),['checkbox']],['read_value',T('value of'),valueKinds]
]) {
 Blockly.Blocks['mb_' + type] = {init() {
   this.appendDummyInput().appendField(label).appendField(dropdown(kinds),'COMPONENT');
   if (type.startsWith('read_')) this.setOutput(true);
   else { if(type !== 'show_page') this.appendValueInput('VALUE').appendField(T('to')); this.setPreviousStatement(true); this.setNextStatement(true); }
   this.setColour(210);
 }};
}
Blockly.Blocks.mb_multiline = {
 init(){this.text_='';this.appendDummyInput().appendField(new Blockly.FieldLabelSerializable(T('Text / script')),'SUMMARY');this.setOutput(true);this.setColour(160);this.setTooltip(T('Use Edit text or script to change several lines.'));},
 saveExtraState(){return {text:this.text_};},
 loadExtraState(state){this.text_=String(state.text || '');this.setFieldValue(this.text_.split('\n')[0].slice(0,60) || T('Text / script'),'SUMMARY');}
};
const block = (type, inputs) => ({kind:'block', type, ...(inputs ? {inputs} : {})});
const value = (type, fields) => ({shadow:{type,fields}});
const emptyList=()=>({block:{type:'lists_create_with',extraState:{itemCount:0}}});
const toolbox = {kind:'categoryToolbox',contents:[
 {kind:'category',name:T('Interface and navigation'),colour:210,contents:[block('mb_set_text',{VALUE:value('text',{TEXT:T('New text')})}),block('mb_set_enabled',{VALUE:value('logic_boolean',{BOOL:'TRUE'})}),block('mb_set_value',{VALUE:value('math_number',{NUM:50})}),block('mb_show_page'),block('mb_go_state'),block('mb_open_window'),block('mb_close_window'),block('mb_message',{VALUE:value('text',{TEXT:T('Hello!')})}),block('mb_read_text'),block('mb_read_checked'),block('mb_read_value')]},
 {kind:'category',name:T('Variables and data'),colour:330,contents:[block('mb_assign',{VALUE:value('math_number',{NUM:0})}),block('mb_variable'),{kind:'block',type:'lists_create_with',extraState:{itemCount:0}}]},
 {kind:'category',name:T('Conditions'),colour:120,contents:[block('mb_if',{CONDITION:value('logic_boolean',{BOOL:'TRUE'})}),block('logic_boolean')]},
 {kind:'category',name:T('Loops'),colour:120,contents:[block('mb_repeat',{COUNT:value('math_number',{NUM:3})})]},
 {kind:'category',name:T('Operations'),colour:230,contents:[block('mb_binary',{LEFT:value('math_number',{NUM:0}),RIGHT:value('math_number',{NUM:0})}),block('math_number')]},
 {kind:'category',name:T('Text'),colour:160,contents:[block('text'),block('mb_multiline'),block('mb_join',{LEFT:value('text',{TEXT:T('Hello, ')}),RIGHT:value('text',{TEXT:'Linux'})})]},
 {kind:'category',name:T('Events'),colour:210,contents:[{kind:'label',text:T('The current event sits at the top of the flow.')},{kind:'button',text:T('Connect another event…'),callbackKey:'MAKEBENCH_EVENT'}]},
 {kind:'category',name:T('Tasks'),colour:20,contents:[block('mb_run',{PROGRAM:value('text',{TEXT:'uname'}),ARGUMENTS:emptyList()}),block('mb_script',{SOURCE:value('text',{TEXT:T('printf "Hello, Linux\\n"')}),ARGUMENTS:emptyList()}),block('mb_log',{VALUE:value('text',{TEXT:T('All set')})}),block('mb_ask',{PROMPT:value('text',{TEXT:T('What is your name?')}),OPTIONS:emptyList()}),block('mb_confirm',{PROMPT:value('text',{TEXT:T('Do you want to continue?')})})]},
 {kind:'category',name:'Terminal',colour:20,contents:[block('mb_terminal_start',{PROGRAM:value('text',{TEXT:''}),ARGUMENTS:emptyList()}),block('mb_terminal_send',{VALUE:value('text',{TEXT:'help\n'})}),block('mb_terminal_stop')]},
 {kind:'category',name:T('Your functions'),colour:290,contents:[{kind:'button',text:T('New function…'),callbackKey:'MAKEBENCH_FUNCTION'},block('mb_call_function'),block('mb_call_value'),block('mb_return')]}
]};

function compileWorkspace() {
 const errors = [];
 const isFunction=current?.flow?.kind==='function', hatType=isFunction?'mb_function':'mb_event';
 const hats = workspace.getTopBlocks(false).filter(b => b.type === hatType);
 const hat = hats[0];
 if(hats.length !== 1) errors.push(T(isFunction?'Keep a single function header here.':'Keep a single event in this flow.'));
 if(workspace.getTopBlocks(false).some(b => b !== hat && !b.isInsertionMarker())) errors.push(T('There are loose blocks. Connect them to the event or remove them.'));
 function base(b, op) { const n={id:b.id,op}; const comment=b.getCommentText(); if(comment) n.comment=comment; return n; }
 function expr(b) {
   if(!b) throw Error(T('A value input is missing.'));
   if(!b.isEnabled()) throw Error(T('There is a disabled value. Enable it to generate code.'));
   const n = base(b, 'literal');
   if(b.type==='mb_multiline') n.value=b.text_;
   else if(b.type === 'text') n.value=b.getFieldValue('TEXT');
   else if(b.type === 'math_number') n.value=Number(b.getFieldValue('NUM'));
   else if(b.type === 'logic_boolean') n.value=b.getFieldValue('BOOL')==='TRUE';
   else if(b.type==='lists_create_with') {n.op='list';n.items=[];for(let index=0;b.getInput('ADD'+index);index++)n.items.push(expr(b.getInputTargetBlock('ADD'+index)));}
   else if(b.type==='mb_variable') {n.op='variable'; n.name=b.getFieldValue('NAME');n.scope=b.getFieldValue('SCOPE')||'project';if(n.scope==='project')delete n.scope;}
   else if(b.type.startsWith('mb_read_')) {n.op='read'; n.attribute=b.type.slice(8); n.component=b.getFieldValue('COMPONENT');}
   else if(b.type==='mb_call_value') call(b,n);
   else if(['mb_binary','mb_join'].includes(b.type)) {n.op=b.type.slice(3);n.left=expr(b.getInputTargetBlock('LEFT'));n.right=expr(b.getInputTargetBlock('RIGHT'));if(n.op==='binary')n.operator=b.getFieldValue('OP');}
   else throw Error(T('Unknown value block: ') + b.type);
   return n;
 }
 function call(b,n) {
   n.op='call_function';n.function=b.getFieldValue('FUNCTION');
   if(n.function==='@missing')throw Error(T('Choose a function to call.'));
   n.args=[];for(let i=0;i<b.argCount_;i++)n.args.push(expr(b.getInputTargetBlock('ARG'+i)));
 }
 function chain(first) {
   const items=[]; let b=first;
   while(b) {
     if(!b.isEnabled()) throw Error(T('Disabled block: enable or remove it to generate code.'));
     const op=b.type.slice(3), n=base(b,op);
     if(op.startsWith('terminal_')){n.component=b.getFieldValue('COMPONENT');if(op==='terminal_start'){n.program=expr(b.getInputTargetBlock('PROGRAM'));n.arguments=expr(b.getInputTargetBlock('ARGUMENTS'));}if(op==='terminal_send')n.value=expr(b.getInputTargetBlock('VALUE'));}
     if(['log','message','set_text','set_enabled','set_value','assign','call'].includes(op)) n.value=expr(b.getInputTargetBlock('VALUE'));
     if(['set_text','set_enabled','set_value','show_page'].includes(op)) n.component=b.getFieldValue('COMPONENT');
     if(op==='assign') {n.name=b.getFieldValue('NAME');n.scope=b.getFieldValue('SCOPE')||'project';if(n.scope==='project')delete n.scope;}
     else if(op==='go_state')n.state=b.getFieldValue('STATE');
     else if(op==='open_window'){n.window=b.getFieldValue('WINDOW');n.close_current=b.getFieldValue('CLOSE')==='TRUE';}
     else if(op==='call') n.function=b.getFieldValue('FUNCTION');
     else if(op==='call_function') call(b,n);
     else if(op==='return'){if(!isFunction)throw Error(T('“Return” only works inside a function.'));const v=b.getInputTargetBlock('VALUE');if(v)n.value=expr(v);}
     else if(op==='run' || op==='script') {n[op==='run'?'program':'source']=expr(b.getInputTargetBlock(op==='run'?'PROGRAM':'SOURCE'));n.arguments=expr(b.getInputTargetBlock('ARGUMENTS'));n.admin=b.getFieldValue('ADMIN')==='TRUE';}
     else if(op==='ask') {n.kind=b.getFieldValue('KIND');n.name=b.getFieldValue('NAME');n.scope=b.getFieldValue('SCOPE')||'project';if(n.scope==='project')delete n.scope;n.prompt=expr(b.getInputTargetBlock('PROMPT'));n.options=expr(b.getInputTargetBlock('OPTIONS'));}
     else if(op==='confirm') n.prompt=expr(b.getInputTargetBlock('PROMPT'));
     else if(op==='if') {n.condition=expr(b.getInputTargetBlock('CONDITION'));n.then=chain(b.getInputTargetBlock('THEN'));n.else=chain(b.getInputTargetBlock('ELSE'));}
     else if(op==='repeat') {n.count=expr(b.getInputTargetBlock('COUNT'));n.body=chain(b.getInputTargetBlock('BODY'));}
     else if(!['log','message','set_text','set_enabled','set_value','show_page','assign','go_state','open_window','close_window','terminal_start','terminal_send','terminal_stop','call_function','return'].includes(op)) throw Error(T('Unknown operation: ') + b.type);
     items.push(n); b=b.getNextBlock();
   }
   return items;
 }
 let body=null;
 try { if(hat) body=chain(hat.getInputTargetBlock('DO')); } catch(e) { errors.push(e.message); }
 return {body: errors.length ? null : body, errors};
}
function stateFor(node, isValue=false) {
 let type='mb_'+node.op, fields={}, inputs={};
 if(node.op==='literal') {
   if(typeof node.value==='string') {type='text';fields.TEXT=node.value;}
   else if(typeof node.value==='boolean') {type='logic_boolean';fields.BOOL=node.value?'TRUE':'FALSE';}
   else {type='math_number';fields.NUM=node.value;}
 }
 if(node.op==='list') {type='lists_create_with';node.items.forEach((item,index)=>inputs['ADD'+index]={block:stateFor(item,true)});}
 if(node.op==='run' || node.op==='script') fields.ADMIN=node.admin?'TRUE':'FALSE';
 if(node.op==='ask') fields.KIND=node.kind;
 if(node.component) fields.COMPONENT=node.component;
 if(node.name) fields.NAME=node.name;
 if(['variable','assign','ask'].includes(node.op))fields.SCOPE=node.scope||'project';
 if(node.op==='go_state')fields.STATE=node.state;
 if(node.op==='open_window'){fields.WINDOW=node.window;fields.CLOSE=node.close_current?'TRUE':'FALSE';}
 if(node.function) fields.FUNCTION=node.function;
 if(node.op==='call_function'){node.args.forEach((item,index)=>inputs['ARG'+index]={block:stateFor(item,true)});}
 if(node.operator) fields.OP=node.operator;
 if(node.op==='read') type='mb_read_'+node.attribute;
 for(const [key,name] of [['value','VALUE'],['left','LEFT'],['right','RIGHT'],['condition','CONDITION'],['count','COUNT'],['program','PROGRAM'],['source','SOURCE'],['arguments','ARGUMENTS'],['prompt','PROMPT'],['options','OPTIONS']]) if(node[key] && typeof node[key]==='object') inputs[name]={block:stateFor(node[key],true)};
 for(const [key,name] of [['then','THEN'],['else','ELSE'],['body','BODY']]) if(node[key]?.length) inputs[name]={block:chainState(node[key])};
 const state={type,id:node.id,fields,inputs};
 if(node.op==='literal' && typeof node.value==='string' && node.value.includes('\n')){state.type='mb_multiline';state.fields={};state.extraState={text:node.value};}
 if(node.op==='list')state.extraState={itemCount:node.items.length};
 if(node.op==='call_function'){state.extraState={count:node.args.length};if(isValue)state.type='mb_call_value';}
 if(node.comment) state.icons={comment:{text:node.comment}};
 return state;
}
function chainState(nodes) { const first=stateFor(nodes[0]); let tail=first; for(const node of nodes.slice(1)){tail.next={block:stateFor(node)};tail=tail.next.block;} return first; }
function rebuild(flow) {
 workspace.clear();
 const state={type:flow.kind==='function'?'mb_function':'mb_event',id:'event_'+flow.id,x:40,y:40,fields:{TITLE:flow.title||flow.name},inputs:{}};
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
     // The neutral model is the authority. The saved view is used only when it matches.
     if(flow.body!==null && canonical(compileWorkspace().body)!==canonical(flow.body)) rebuild(flow);
   } catch(e) { if(flow.body===null){bridge.problem(T('Could not recover the draft: ')+e.message);current=null;} else rebuild(flow); }
   if(current) {
     const hat=workspace.getAllBlocks(false).find(b=>['mb_event','mb_function'].includes(b.type));
     if(hat){hat.setFieldValue(flow.title||flow.name,'TITLE');hat.setDeletable(false);hat.setMovable(false);hat.setEditable(false);}
   }
 }
 document.getElementById('empty').style.display=current?'none':'flex';
 workspace.getAllBlocks(false).forEach(block=>{
   if(block.type==='mb_call')block.setTooltip(()=>{
     const name=block.getFieldValue('FUNCTION');const info=(context.function_info||[]).find(item=>item.name===name);
     return info?info.signature+'\n'+info.description:T('Function missing from your file. Open Code to define it.');
   });
   if(['mb_run','mb_script'].includes(block.type))block.setTooltip(()=>block.getFieldValue('ADMIN')==='TRUE'?T('Asks for authorization through the system dialog. Makebench never receives passwords.'):T('Runs a system program, with separate arguments.'));
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
   b.text_=text;b.setFieldValue(text.split('\n')[0].slice(0,60) || T('Text / script'),'SUMMARY');b.render();
 } finally {Blockly.Events.enable();}
 bridge.pending(current.token);report();return true;
}
window.makebench={setDocument,flush,compileWorkspace,textValue,setTextValue, get workspace(){return workspace;}};
new QWebChannel(qt.webChannelTransport, channel => {
 bridge=channel.objects.bridge;
 // Blockly 13 provides an explicit serializer for loose comments.
 try {Blockly.serialization.registry.register('workspaceComments',new Blockly.serialization.workspaceComments.WorkspaceCommentSerializer());} catch(e) { /* Already registered in this version. */ }
 workspace=Blockly.inject('workspace',{toolbox,renderer:'zelos',media:'vendor/blockly/media/',sounds:false,trashcan:true,comments:true,collapse:true,disable:false,maxBlocks:5000,maxUndo:0,zoom:{controls:true,wheel:true,startScale:0.85},grid:{spacing:24,length:2,colour:'var(--mb-grid)',snap:false}});
 workspace.registerButtonCallback('MAKEBENCH_EVENT',()=>bridge.command('new_event'));
 workspace.registerButtonCallback('MAKEBENCH_FUNCTION',()=>bridge.command('new_function'));
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

window.makebench.selectedFunction=function(){const block=Blockly.getSelected();return block?.type==='mb_call'?block.getFieldValue('FUNCTION'):['mb_call_function','mb_call_value'].includes(block?.type)?'@block:'+block.getFieldValue('FUNCTION'):null;};
Blockly.ContextMenuRegistry.registry.register({id:'makebench_python',scopeType:Blockly.ContextMenuRegistry.ScopeType.BLOCK,
 displayText:T('Go to Python'),weight:50,preconditionFn:()=>'enabled',callback:()=>bridge.command('python')});
Blockly.ContextMenuRegistry.registry.register({id:'makebench_function',scopeType:Blockly.ContextMenuRegistry.ScopeType.BLOCK,
 displayText:T('Open function'),weight:51,preconditionFn:scope=>['mb_call','mb_call_function','mb_call_value'].includes(scope.block.type)?'enabled':'hidden',callback:()=>bridge.command('function')});

for(const type of ['mb_assign','mb_variable','mb_ask']) {
 const original=Blockly.Blocks[type].init;
 Blockly.Blocks[type].init=function(){
   original.call(this);
   const picker=new Blockly.FieldDropdown(()=>{
     const groups={project:T('Project-wide'),window:T('This window'),local:T('This flow')};
     const values=[[T('Choose variable…'),'@none']];
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

// Marks belong to the IDE; they never change the blocks' semantics.
Blockly.ContextMenuRegistry.registry.register({id:'makebench_breakpoint',scopeType:Blockly.ContextMenuRegistry.ScopeType.BLOCK,
 displayText:()=> T('Toggle breakpoint'),preconditionFn:scope=>['mb_event','mb_function'].includes(scope.block.type)?'hidden':'enabled',weight:1,
 callback:scope=>{if(current)bridge.toggleBreakpoint(current.flow.id,scope.block.id);}});
window.makebench.setBreakpoints=function(ids){if(workspace)for(const block of workspace.getAllBlocks(false))block.setWarningText(ids.includes(block.id)?T('Breakpoint'):null,'makebench-breakpoint');};
