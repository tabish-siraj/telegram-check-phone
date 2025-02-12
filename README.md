# Telegram Number Check Backend

This project is the backend service for the Telegram Number Check application. It provides APIs to check the validity and status of phone numbers on Telegram.

## Features

- Validate phone numbers
- Check the status of phone numbers on Telegram
- RESTful API endpoints

## Technologies Used

- Python
- FastAPI
- Telethon SDK

## Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/tabish-siraj/telegram-number-check-backend.git
    ```
2. Navigate to the project directory:
    ```sh
    cd telegram-number-check-backend
    ```
3. Install dependencies:
    ```sh
    pip install -r requirements.txt
    ```

## Configuration

1. Create a `.env` file in the root directory and add the following environment variables:
    ```env
    TELEGRAM_API_ID
    TELEGRAM_API_HASH
    TELEGRAM_PHONE
    ```

## Usage

1. Start the server:
    ```sh
    python main.py
    ```
2. The server will be running at `http://localhost:your_port_number`.

## API Endpoints

- `POST / ` - Check the validity and status of a phone number on Telegram.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any changes.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contact

For any inquiries, please contact [your email address].
