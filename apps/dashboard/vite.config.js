import { defineConfig } from 'vite';
export default defineConfig({
    resolve: {
        extensions: ['.tsx', '.ts', '.jsx', '.js', '.mjs', '.json']
    },
    server: {
        host: '127.0.0.1',
        port: 4173
    }
});
