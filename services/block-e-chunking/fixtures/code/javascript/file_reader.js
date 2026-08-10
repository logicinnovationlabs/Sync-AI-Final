/**
 * File reading utilities
 */

const fs = require('fs').promises;
const path = require('path');

class FileReader {
  constructor(basePath) {
    this.basePath = basePath;
  }

  async read(filepath) {
    const fullPath = path.join(this.basePath, filepath);
    try {
      return await fs.readFile(fullPath, 'utf-8');
    } catch {
      return null;
    }
  }

  async readJSON(filepath) {
    const content = await this.read(filepath);
    if (!content) return null;
    try {
      return JSON.parse(content);
    } catch {
      return null;
    }
  }

  async exists(filepath) {
    const fullPath = path.join(this.basePath, filepath);
    try {
      await fs.access(fullPath);
      return true;
    } catch {
      return false;
    }
  }

  async listFiles(dirpath) {
    const fullPath = path.join(this.basePath, dirpath);
    try {
      return await fs.readdir(fullPath);
    } catch {
      return [];
    }
  }
}

module.exports = FileReader;
