import {defineConfig} from 'vite';
import {fileURLToPath} from 'node:url';
export default defineConfig({define:{'process.env.NODE_ENV':JSON.stringify('production')},build:{outDir:'../election-news-server/static/react',emptyOutDir:false,lib:{entry:fileURLToPath(new URL('./src/main.jsx',import.meta.url)),formats:['es'],fileName:()=> 'newsroom.js',cssFileName:'newsroom'},sourcemap:false}});
