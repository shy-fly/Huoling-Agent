/*!
 * Tabler icons sourced from the Iconify tabler collection.
 * Copyright (c) 2020-2026 Paweł Kuna
 * https://github.com/iconify/icon-sets/blob/master/json/tabler.json
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */
const paths = {
    flask: "M6.1 15h11.8M14 3v7.342A6 6 0 0 1 15.318 21H8.683A6 6 0 0 1 10 10.34V3zM9 3h6",
    send: "M12 5v14m6-8l-6-6m-6 6l6-6",
    external: "M17 7L7 17M8 7h9v9",
    book: "M3 19a9 9 0 0 1 9 0a9 9 0 0 1 9 0M3 6a9 9 0 0 1 9 0a9 9 0 0 1 9 0M3 6v13m9-13v13m9-13v13",
    chevron: "m6 9l6 6l6-6",
    alert: "M3 12a9 9 0 1 0 18 0a9 9 0 0 0-18 0m9-4v4m0 4h.01",
    sidebar: "M4 6a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2zM9 4v16",
    edit: "M7 7h-1a2 2 0 0 0 -2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2 -2v-1M20.4 7.6a2 2 0 0 0 -2.8 -2.8l-8.6 8.6v3h3zM16 6l3 3",
    loader: "M12 3a9 9 0 1 0 9 9",
};

export default function Icon({ name, size = 18, className }: {
    name: keyof typeof paths;
    size?: number;
    className?: string;
}) {
    return (
        <svg aria-hidden="true" focusable="false" className={className} width={size} height={size} viewBox="0 0 24 24"
            fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d={paths[name]} />
        </svg>
    );
}
