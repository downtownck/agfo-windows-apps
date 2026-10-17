<?php
// AGFO AI Manager — isolated image prompt regression tests (CLI only). Run: php tests/image-prompt-tests.php
if ( PHP_SAPI !== 'cli' ) { exit; }
define('ABSPATH','/');
$GLOBALS['opts']=[]; $GLOBALS['calls']=[]; $GLOBALS['mock_reply']=null; $GLOBALS['post']=null;
if (!function_exists('get_option')) { function get_option($k,$d=false){return $GLOBALS['opts'][$k]??$d;} }
if (!function_exists('update_option')) { function update_option($k,$v,$a=null){$GLOBALS['opts'][$k]=$v;return true;} }
if (!function_exists('delete_option')) { function delete_option($k){unset($GLOBALS['opts'][$k]);return true;} }
if (!function_exists('apply_filters')) { function apply_filters($t,$v){return $v;} }
if (!function_exists('do_action')) { function do_action(){} }
if (!function_exists('add_action')) { function add_action(){} }
if (!function_exists('sanitize_key')) { function sanitize_key($k){return preg_replace('/[^a-z0-9_\-]/','',strtolower((string)$k));} }
if (!function_exists('sanitize_text_field')) { function sanitize_text_field($s){return trim(preg_replace('/[\r\n\t ]+/',' ',strip_tags((string)$s)));} }
if (!function_exists('sanitize_textarea_field')) { function sanitize_textarea_field($s){return trim(strip_tags((string)$s));} }
if (!function_exists('wp_strip_all_tags')) { function wp_strip_all_tags($s){return strip_tags((string)$s);} }
if (!function_exists('strip_shortcodes')) { function strip_shortcodes($s){return preg_replace('/\[[^\]]+\]/','',$s);} }
if (!function_exists('wp_json_encode')) { function wp_json_encode($d){return json_encode($d,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);} }
if (!function_exists('get_post')) { function get_post($id){return $GLOBALS['post'];} }
if (!function_exists('agfo_get_priority_api_key')) { function agfo_get_priority_api_key(){return ['key'=>'k','chat_url'=>'https://x/chat','code'=>$GLOBALS['chat_code']??'openai','model'=>$GLOBALS['chat_model']??'gpt-4.1','auth'=>[]];} }
if (!function_exists('agfo_openai_model_is_reasoning')) { function agfo_openai_model_is_reasoning($m){return strpos($m,'gpt-5')===0;} }
if (!function_exists('agfo_model_temperature_status')) { function agfo_model_temperature_status($c,$m){return 'unknown';} }
if (!function_exists('agfo_api_post')) { function agfo_api_post($u,$h,$b,$o){$GLOBALS['calls'][]=['url'=>$u,'body'=>json_decode($b,true),'opt'=>$o];$r=$GLOBALS['mock_reply'];return $r===null?['http_code'=>500,'body'=>'']:['http_code'=>200,'body'=>json_encode(['choices'=>[['message'=>['content'=>$r]]]])];} }
if (!function_exists('agfo_api_registry')) { function agfo_api_registry(){return ['openai'=>['label'=>'OpenAI'],'fal'=>['label'=>'fal']];} }
if (!function_exists('agfo_get_api_key')) { function agfo_get_api_key($c){return 'k';} }
if (!class_exists('WP_Error', false)) { class WP_Error{public $c;public $m;function __construct($c,$m){$this->c=$c;$this->m=$m;}function get_error_message(){return $this->m;}} }
if (!function_exists('is_wp_error')) { function is_wp_error($x){return $x instanceof WP_Error;} }
$root=dirname(__DIR__);
require "$root/includes/adapters/class-adapter-image.php";
require "$root/includes/image/class-image-prompt-library.php";
require "$root/includes/image/class-image-generator.php";
$pass=0;$fail=0;
if (!function_exists('agfo_aim_test_ok')) { function agfo_aim_test_ok($c,$n){global $pass,$fail; if($c){$pass++;} else {$fail++; echo "FAIL: $n\n";}} }
$G='AGFO_AIM_Image_Generator'; $L='AGFO_AIM_Image_Prompt_Library'; $A='AGFO_AIM_Image_Adapter';
$post=(object)['post_title'=>'Özgürlük ve Sorumluluk','post_content'=>str_repeat('Sartre der ki insan özgürlüğe mahkûmdur. ',400)];
$GLOBALS['post']=$post;

// T01 budgets
agfo_aim_test_ok($A::prompt_budget('minimax','image-01')===1400,'T01 minimax budget');
agfo_aim_test_ok($A::prompt_budget('fal','fal-ai/flux/dev')===1800,'T01 flux budget');
agfo_aim_test_ok($A::prompt_budget('fal','fal-ai/recraft-v3')===950,'T01 recraft budget');
agfo_aim_test_ok($A::prompt_budget('gemini','imagen-4.0-generate-001')===1800,'T01 imagen budget');
agfo_aim_test_ok($A::prompt_budget('openai','gpt-image-2')===6000,'T01 gpt-image budget');

// T02 legacy compose: subject first and within budget for every preset/provider
$subj=str_repeat('A lone woman on a ferry deck at dawn. ',40);
foreach($L::defaults() as $k=>$r){ foreach([['minimax','image-01'],['fal','fal-ai/flux/dev'],['fal','fal-ai/recraft-v3'],['gemini','imagen-4.0-generate-001'],['openai','gpt-image-2']] as [$p,$m]){
  $pr=$G::compose_prompt(['preset'=>$k,'subject'=>$subj,'provider'=>$p,'model'=>$m,'extra'=>'warm tones']);
  agfo_aim_test_ok(mb_strlen($pr)<=$A::prompt_budget($p,$m),"T02 legacy len $k $p ".mb_strlen($pr));
  agfo_aim_test_ok(strpos($pr,'SUBJECT:')===0,"T02 subject first $k $p");
}}
// T03 art-directed compose
foreach([['minimax','image-01'],['fal','fal-ai/flux/dev'],['openai','gpt-image-2']] as [$p,$m]){
  $pr=$G::compose_prompt(['preset'=>'featured_philosophical','subject'=>$subj,'art_directed'=>true,'provider'=>$p,'model'=>$m,'aspect'=>'16:9']);
  agfo_aim_test_ok(mb_strlen($pr)<=$A::prompt_budget($p,$m),"T03 AD len $p");
  agfo_aim_test_ok(strpos($pr,'A lone woman')===0,"T03 AD starts with brief $p");
  agfo_aim_test_ok(strpos($pr,'Aspect ratio 16:9.')!==false,"T03 aspect tail $p");
  agfo_aim_test_ok(strpos($pr,'ART DIRECTION')===false,"T03 no rule dump $p");
}
$pr=$G::compose_prompt(['preset'=>'featured_philosophical','subject'=>'x scene.','art_directed'=>true,'provider'=>'fal','model'=>'fal-ai/flux/dev']);
agfo_aim_test_ok(stripos($pr,'religious')===false && stripos($pr,'No text')===false,'T03 fal tail has no negated nouns');
$pr=$G::compose_prompt(['preset'=>'album_cover','subject'=>'scene without title.','art_directed'=>true,'provider'=>'openai','model'=>'gpt-image-2','title_text'=>'Gül Yüzlüm']);
agfo_aim_test_ok(strpos($pr,'"Gül Yüzlüm"')!==false,'T03 title appended when AD omitted it');
$pr=$G::compose_prompt(['preset'=>'album_cover','subject'=>'scene with "Gül Yüzlüm" title.','art_directed'=>true,'provider'=>'openai','model'=>'gpt-image-2','title_text'=>'Gül Yüzlüm']);
agfo_aim_test_ok(substr_count($pr,'Gül Yüzlüm')===1,'T03 title not duplicated');

// T04 art director system by mode
$s=$G::art_director_system($L::get('infographic'),6000,['language'=>'Türkçe']);
agfo_aim_test_ok(strpos($s,'information designer')!==false && strpos($s,'Never invent figures')!==false && strpos($s,'Türkçe')!==false,'T04 infographic system');
$s=$G::art_director_system($L::get('album_cover'),6000,['title_text'=>'Sevda']);
agfo_aim_test_ok(strpos($s,'record label')!==false && strpos($s,'"Sevda"')!==false && strpos($s,'Cemal Gürkan Kara')!==false,'T04 cover system');
$s=$G::art_director_system($L::get('editorial_article'),1400,[]);
agfo_aim_test_ok(strpos($s,'photo editor')!==false && strpos($s,'no lettering')!==false && strpos($s,'Never name a forbidden element')!==false,'T04 scene system');
preg_match('/about (\d+) words/',$s,$mm); agfo_aim_test_ok((int)$mm[1]>=60 && (int)$mm[1]<=170,'T04 small budget words '.$mm[1]);

// T05 legacy override migration
$old=json_decode(file_get_contents(__DIR__.'/fixture-image-prompts-16.16.json'),true);
$GLOBALS['opts'][$L::OPTION_KEY]=$old;
$old['editorial_article']['prompt']='MY CUSTOM PROMPT';
$GLOBALS['opts'][$L::OPTION_KEY]=$old;
$all=$L::get_all();
agfo_aim_test_ok($all['featured_philosophical']['prompt']===$L::defaults()['featured_philosophical']['prompt'],'T05 frozen old default replaced');
agfo_aim_test_ok($all['editorial_article']['prompt']==='MY CUSTOM PROMPT','T05 real customisation kept');
agfo_aim_test_ok($all['infographic']['mode']==='infographic' && $all['album_cover']['mode']==='cover','T05 modes');
$GLOBALS['opts'][$L::OPTION_KEY]['featured_philosophical']['mode']='bogus';
agfo_aim_test_ok($L::get_all()['featured_philosophical']['mode']==='scene','T05 saved mode ignored');

// T06 save_overrides does not freeze defaults
$posted=[]; foreach($L::defaults() as $k=>$r){$posted[$k]=['label'=>$r['label'],'aspect'=>$r['aspect'],'allow_text'=>$r['allow_text'],'prompt'=>$r['prompt']];}
$posted['corporate_technical']['prompt']='custom corp';
$L::save_overrides($posted);
$saved=$GLOBALS['opts'][$L::OPTION_KEY];
agfo_aim_test_ok(!isset($saved['featured_philosophical']['prompt']),'T06 unchanged default not stored');
agfo_aim_test_ok($saved['corporate_technical']['prompt']==='custom corp','T06 custom stored');
agfo_aim_test_ok(!isset($saved['infographic']['mode']),'T06 mode not stored');
$L::reset();

// T07 settings art_director
agfo_aim_test_ok($G::settings()['art_director']===1,'T07 default on');
$G::save_settings(['art_director'=>'0']); agfo_aim_test_ok($G::settings()['art_director']===0,'T07 off persists');
$G::save_settings(['provider'=>'openai']); agfo_aim_test_ok($G::settings()['art_director']===0,'T07 unrelated save keeps value');
$G::save_settings(['art_director'=>'1']); agfo_aim_test_ok($G::settings()['art_director']===1,'T07 on again');

// T08 adapter bodies
$r=$A::build_request(['code'=>'gemini','model'=>'gemini-2.5-flash-image','key'=>'k'],['prompt'=>'p','aspect'=>'9:16']);
agfo_aim_test_ok(($r['body']['generationConfig']['imageConfig']['aspectRatio']??'')==='9:16','T08 gemini aspect');
$r=$A::build_request(['code'=>'gemini','model'=>'imagen-4.0-generate-001','key'=>'k'],['prompt'=>'p','aspect'=>'16:9']);
agfo_aim_test_ok(($r['body']['parameters']['aspectRatio']??'')==='16:9','T08 imagen unchanged');
$r=$A::build_request(['code'=>'fal','model'=>'fal-ai/flux-pro/v1.1-ultra','key'=>'k'],['prompt'=>'p','aspect'=>'9:16']);
agfo_aim_test_ok(($r['body']['aspect_ratio']??'')==='9:16' && !isset($r['body']['image_size']),'T08 flux ultra aspect');
$r=$A::build_request(['code'=>'fal','model'=>'fal-ai/flux/dev','key'=>'k'],['prompt'=>'p','aspect'=>'9:16']);
agfo_aim_test_ok(($r['body']['image_size']??'')==='portrait_16_9','T08 flux dev unchanged');
$r=$A::build_request(['code'=>'openai','model'=>'gpt-image-2','key'=>'k'],['prompt'=>'p','aspect'=>'16:9','quality'=>'high']);
agfo_aim_test_ok($r['body']['size']==='1536x1024' && $r['body']['quality']==='high','T08 openai unchanged');

// T09 brief with AD + cleaning
$GLOBALS['calls']=[]; $GLOBALS['mock_reply']="```\nPrompt: A middle-aged man at a rain-streaked window.\n```";
$b=$G::build_subject_brief(1,'content',['preset'=>'featured_philosophical','provider'=>'openai','model'=>'gpt-image-2','art_director'=>true]);
agfo_aim_test_ok($b['art_directed']===true && $b['brief']==='A middle-aged man at a rain-streaked window.','T09 AD brief cleaned: '.$b['brief']);
agfo_aim_test_ok($GLOBALS['calls'][0]['opt']['source']==='image_studio_art_director','T09 source tag');
agfo_aim_test_ok(abs($GLOBALS['calls'][0]['body']['temperature']-0.8)<1e-9 && $GLOBALS['calls'][0]['body']['max_tokens']===1500,'T09 temp/tokens');
agfo_aim_test_ok(strpos($GLOBALS['calls'][0]['body']['messages'][1]['content'],'SOURCE TEXT')!==false,'T09 user msg');
// 2-arg BC call
$GLOBALS['calls']=[]; $b=$G::build_subject_brief(1,'content');
agfo_aim_test_ok(count($GLOBALS['calls'])===1 && isset($b['brief']),'T09 two-arg call still works');
// AD off -> legacy system
$GLOBALS['calls']=[]; $b=$G::build_subject_brief(1,'content',['art_director'=>false]);
agfo_aim_test_ok($GLOBALS['calls'][0]['opt']['source']==='image_studio_brief' && $b['art_directed']===false,'T09 legacy brief when off');
// failure -> fallback title
$GLOBALS['mock_reply']=null; $b=$G::build_subject_brief(1,'content',['art_director'=>true]);
agfo_aim_test_ok($b['brief']==='Özgürlük ve Sorumluluk' && $b['art_directed']===false,'T09 fallback title');

// T10 reasoning model body
$GLOBALS['chat_model']='gpt-5.4'; $GLOBALS['calls']=[]; $GLOBALS['mock_reply']='x';
$G::build_subject_brief(1,'content',['art_director'=>true]);
$bd=$GLOBALS['calls'][0]['body'];
agfo_aim_test_ok($bd['reasoning_effort']==='low' && $bd['max_tokens']===6000 && !isset($bd['temperature']),'T10 reasoning body');
$GLOBALS['chat_model']='gemini-2.5-pro'; $GLOBALS['chat_code']='gemini'; $GLOBALS['calls']=[];
$G::build_subject_brief(1,'content',['art_director'=>true]);
agfo_aim_test_ok($GLOBALS['calls'][0]['body']['generationConfig']['maxOutputTokens']===4096,'T10 gemini tokens');
$GLOBALS['chat_code']='openai'; $GLOBALS['chat_model']='gpt-4.1';

// T11 prompt scope: operator only
$GLOBALS['post']=null; $GLOBALS['calls']=[]; $GLOBALS['mock_reply']='An old oud player in a Baku courtyard at dusk.';
$b=$G::build_subject_brief(0,'prompt',['extra'=>'bir udi, Bakü','art_director'=>true]);
agfo_aim_test_ok($b['art_directed'] && strpos($GLOBALS['calls'][0]['body']['messages'][1]['content'],'OPERATOR NOTE')!==false,'T11 operator-only AD');
$b=$G::build_subject_brief(0,'prompt',['extra'=>'','art_director'=>true]);
agfo_aim_test_ok($b['brief']==='' ,'T11 empty everything -> empty');
$GLOBALS['post']=$post;

// T12 public API surface still present
foreach(['defaults','mandatory_guardrails','get_all','get','default_key','public_catalog','save_overrides','reset'] as $m) agfo_aim_test_ok(method_exists($L,$m),"T12 lib $m");
foreach(['register_hooks','settings','save_settings','available_providers','effective_default','build_subject_brief','compose_prompt','generate','ajax_generate','ajax_set_featured','ajax_preview_prompt'] as $m) agfo_aim_test_ok(method_exists($G,$m),"T12 gen $m");
echo "PASS $pass / FAIL $fail\n";
exit($fail?1:0);
