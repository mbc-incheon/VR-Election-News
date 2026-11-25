import {useEffect,useState} from 'react';
// All components share the existing WebSocket stream; no second connection.
export function useNewsroom(){const [view,setView]=useState(()=>window.newsroomView||{});useEffect(()=>{const receive=event=>setView(event.detail);window.addEventListener('newsroom:view',receive);setView(window.newsroomView||{});return()=>window.removeEventListener('newsroom:view',receive)},[]);return view}
