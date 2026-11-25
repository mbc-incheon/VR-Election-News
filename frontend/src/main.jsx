import React from 'react';
import {createRoot} from 'react-dom/client';
import {useNewsroom} from './hooks/useNewsroom.js';
import {regionSummary} from './model.js';
import Header from './components/Header.jsx';
import CandidateCard from './components/CandidateCard.jsx';
import TurnoutBar from './components/TurnoutBar.jsx';
import ArticleList from './components/ArticleList.jsx';
import ReplayGraph from './components/ReplayGraph.jsx';
import './style.css';
const notify=(name,detail)=>window.dispatchEvent(new CustomEvent(name,{detail}));
class Boundary extends React.Component{constructor(props){super(props);this.state={error:false}}static getDerivedStateFromError(){return {error:true}}render(){return this.state.error?<p className="empty">요약 화면을 표시하지 못했습니다. 아래 수치 표를 확인하거나 새로고침해 주세요.</p>:this.props.children}}
function ElectionDashboard(){const view=useNewsroom(),snapshot=view.snapshot||{},summary=regionSummary(snapshot,view.region);return <div className="react-results"><Header region={view.region} mode={snapshot.mode} connection={view.connection?.state||snapshot.connection?.state}/>{summary.rows.length?<><div className="react-candidate-grid">{summary.rows.map((candidate,index)=><CandidateCard key={candidate.candidate_id} candidate={candidate} index={index} selected={view.candidate===candidate.candidate_id} onSelect={()=>notify('newsroom:candidate',candidate.candidate_id)}/>)}</div><TurnoutBar summary={summary}/>{snapshot.mode==='official'&&snapshot.stage==='FINAL_FILE_AGGREGATION'&&<ReplayGraph key={snapshot.mode+'|'+view.region} rows={summary.rows}/>}<p className="react-data-note">{snapshot.mode==='demo'?'가상 후보·가상 수치입니다.':'과거 선거의 공식 파일 집계이며 현재 선거 속보가 아닙니다.'} 후보 카드는 득표수 순으로 표시하며 당선 예측을 제공하지 않습니다.</p></>:<p className="empty">선택 지역의 개표 데이터를 기다리고 있습니다.</p>}</div>}
function NewsArticles(){const view=useNewsroom();return <ArticleList articles={view.articles} selected={view.current?.id} onSelect={id=>notify('newsroom:select-article',id)}/>}
const election=document.getElementById('react-election');if(election)createRoot(election).render(<Boundary><ElectionDashboard/></Boundary>);
const articles=document.getElementById('articles');if(articles){createRoot(articles).render(<Boundary><NewsArticles/></Boundary>);window.newsroomReactLists=true}
