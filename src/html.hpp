#pragma once
#include <string>
#include <vector>
#include <utility>

inline std::string render_index_html(const std::vector<std::pair<std::string, std::string>>& entries, std::size_t max_size_bytes) {
    std::string html;
    html += "<!doctype html><html><head><meta charset=\"utf-8\">";
    html += "<title>Simple File Sharing (C++)</title>";
    html += "<style>body{font-family:sans-serif;margin:2rem;} table{border-collapse:collapse;} td,th{padding:.4rem .6rem;border-bottom:1px solid #ddd;} code{background:#f5f5f5;padding:.1rem .3rem;border-radius:3px;} .muted{color:#777}</style>";
    html += "</head><body>";
    html += "<h1>Simple File Sharing (C++)</h1>";
    if (max_size_bytes == 0) {
        html += "<p class=\"muted\">Max upload size: no limit</p>";
    } else {
        html += "<p class=\"muted\">Max upload size: " + std::to_string(max_size_bytes/1024/1024) + " MB</p>";
    }
    html += "<h2>Upload</h2>";
    html += "<form method=\"POST\" action=\"/upload\" enctype=\"multipart/form-data\">";
    html += "<input type=\"file\" name=\"file\" required> <button type=\"submit\">Upload</button>";
    html += "</form>";
    html += "<p class=\"muted\">Or via curl: <code>curl -F file=@/path/to/file http://127.0.0.1:8000/upload</code></p>";
    html += "<h2>Files</h2>";
    html += "<table><thead><tr><th>ID</th><th>Name</th><th>Actions</th></tr></thead><tbody>";
    if (entries.empty()) {
        html += "<tr><td colspan=3 class=\"muted\">No files yet</td></tr>";
    } else {
        for (auto& kv : entries) {
            html += "<tr>";
            html += "<td><code>" + kv.first + "</code></td>";
            html += "<td>" + kv.second + "</td>";
            html += "<td><a href=\"/download/" + kv.first + "\">download</a> &nbsp;";
            html += "<a href=\"#\" onclick=\"fetch('/delete/" + kv.first + "',{method:'DELETE'}).then(()=>location.reload())\">delete</a></td>";
            html += "</tr>";
        }
    }
    html += "</tbody></table>";
    html += "</body></html>";
    return html;
}
