# Use official Node.js runtime as base image
FROM node:22

# Set working directory inside container
WORKDIR /usr/src/app

# Copy package.json and package-lock.json to working directory
COPY package*.json ./

# Install Node.js dependencies
RUN npm install

# Install Playwright browsers required for your app
RUN npx playwright install

# Copy all project files to working directory
COPY . .

# Tell Docker to expose the port your app listens on
ENV PORT=3000
EXPOSE 3000

# Start your Node.js app using your server.js entry point
CMD ["node", "src/server.js"]
